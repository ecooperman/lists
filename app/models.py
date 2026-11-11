import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship

from .database import Base


class ScrapeStatus(str, enum.Enum):
    not_started = "not_started"
    success = "success"
    failed = "failed"
    unsupported = "unsupported"


# Priority is a fixed 1-5 scale shared by every list (an item may also have
# none set), so sorting
# means the same thing everywhere. Each list may relabel the five levels
# (ItemList.priority_labels); these are what a list without overrides shows.
DEFAULT_PRIORITY_LABELS = ["Low", "Medium", "High", "Critical", "Blocker"]


# What a person can do on a list they're a member of. "owner" is whoever
# created it (exactly one per list) and is the only one who can share, rename,
# lock or delete it; "edit" works with the items; "view" can only read.
ROLE_OWNER = "owner"
ROLE_EDIT = "edit"
ROLE_VIEW = "view"
ROLE_RANK = {ROLE_VIEW: 1, ROLE_EDIT: 2, ROLE_OWNER: 3}


class User(Base):
    """Someone who has signed in (or been invited by email before they have).
    Created on demand from the email Cloudflare Access vouches for - there is
    no password or sign-up form (see app/auth.py)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    # Always stored lowercased (crud.normalize_email).
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Contact(Base):
    """One person's address book entry. A shared list uses its *owner's*
    contacts (see crud.contact_usable_for_list); other members only ever see
    the recipient's name."""

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)

    items = relationship("Item", back_populates="recipient")


class Category(Base):
    """A user-managed label (name + color) a list can optionally belong to -
    same shape as the categories in time-management and trip-planning, but
    one per list rather than several. `text_color` ("dark"/"light") is which
    text reads legibly on `color`, picked by the user rather than computed."""

    __tablename__ = "categories"
    # Names are unique per person (case-insensitively - see
    # crud.category_name_taken), not across everyone.
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_categories_owner_id_name"),)

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, nullable=False)
    text_color = Column(String, nullable=False, default="dark", server_default="dark")
    # User-controlled order (drag on the Categories page); new rows go to the
    # end at max+10, leaving gaps (same pattern as trip-planning).
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")


class ItemList(Base):
    """A named list with a purpose ("Gifts", "Movies to watch", ...). Every
    list has the same item structure - see Item - so a list is just a name
    and a purpose wrapped around its own items."""

    __tablename__ = "lists"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    purpose = Column(String, nullable=True)
    # A locked list can't be deleted until it's unlocked (see crud.delete_list).
    locked = Column(Boolean, nullable=False, default=False)
    # How the list's items are ordered: "manual" (the drag order, sort_order)
    # or "priority" (highest first, ties in manual order). See crud.get_items.
    sort_mode = Column(String, nullable=False, default="manual")
    # This list's own names for priority levels 1-5, or NULL for the defaults.
    # Read/write it through the priority_labels property below.
    _priority_labels = Column("priority_labels", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("Item", back_populates="list")
    owner = relationship("User")
    members = relationship("ListMember", back_populates="list", cascade="all, delete-orphan")
    # No delete cascade: crud.delete_list removes the unfinished requests and
    # leaves the approved ones (their list_id goes NULL).
    invites = relationship("Invite", back_populates="list")

    @property
    def priority_labels(self):
        """Always five labels: this list's override for a level where it set
        one, the default otherwise."""
        stored = self._priority_labels or []
        return [
            stored[i].strip() if i < len(stored) and stored[i] and stored[i].strip() else default
            for i, default in enumerate(DEFAULT_PRIORITY_LABELS)
        ]

    @priority_labels.setter
    def priority_labels(self, value):
        # Store only real overrides: a label that matches its default is kept
        # blank, and a list with no overrides at all is stored as NULL.
        cleaned = None if value is None else [(label or "").strip() for label in value]
        if cleaned:
            cleaned = ["" if label == default else label for label, default in zip(cleaned, DEFAULT_PRIORITY_LABELS)]
        self._priority_labels = cleaned if cleaned and any(cleaned) else None


class ListMember(Base):
    """One person's access to one list, plus how *they* have it arranged: the
    list's position on their index and the category they filed it under are
    per person, so sharing a list never rearranges anyone else's page."""

    __tablename__ = "list_members"

    list_id = Column(Integer, ForeignKey("lists.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role = Column(String, nullable=False)
    # Manual position on this person's lists index, lower first (see
    # crud.reorder_lists). New lists go to the end.
    sort_order = Column(Integer, nullable=False, default=0)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    list = relationship("ItemList", back_populates="members")
    user = relationship("User")
    category = relationship("Category")


INVITE_PENDING = "pending"
INVITE_APPROVED = "approved"
INVITE_DECLINED = "declined"


class Invite(Base):
    """A list owner's request to let someone who has no account yet in, with
    a role on that list. An administrator approves it (the email is added to
    Cloudflare's allowed group and the person is put on the list) or declines
    it. One request per person per list. Approved requests outlive their list
    (list_id goes NULL) so they keep counting against the inviter's allowance."""

    __tablename__ = "invites"
    __table_args__ = (
        UniqueConstraint("list_id", "email", name="uq_invites_list_id_email"),
        # An invite to the app itself has no list, and NULLs never collide in the constraint
        # above - so one per email is enforced here (approved invites whose list was deleted
        # also have no list, but they are not app invites, so they don't count).
        Index("uq_invites_app_email", "email", unique=True, sqlite_where=text("for_app = 1"), postgresql_where=text("for_app")),
    )

    id = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("lists.id"), nullable=True)
    email = Column(String, nullable=False)  # lowercased
    role = Column(String, nullable=False)  # what they get on the list: edit or view
    invited_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False, default=INVITE_PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)
    # True for an invite to the app itself rather than to one list: approving it only
    # lets the person in (no list to put them on). `role` is a placeholder then.
    for_app = Column(Boolean, nullable=False, default=False, server_default=text("0"))

    list = relationship("ItemList", back_populates="invites")
    invited_by = relationship("User")


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("lists.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    url = Column(String, nullable=True)
    needed_by = Column(DateTime, nullable=True)

    done = Column(Boolean, nullable=False, default=False)
    done_at = Column(DateTime, nullable=True)
    # 0-100, how far along a not-yet-done item is. Independent of `done`:
    # checking an item off doesn't touch it (the UI just stops drawing it).
    progress = Column(Integer, nullable=False, default=0)
    # 1-5, lowest to highest (named per list, see ItemList.priority_labels);
    # NULL = no priority set.
    priority = Column(Integer, nullable=True)
    # Manual position within the list, lower first (see crud.reorder_items).
    # New items go to the end.
    sort_order = Column(Integer, nullable=False, default=0)

    scrape_status = Column(Enum(ScrapeStatus), nullable=False, default=ScrapeStatus.not_started)
    scraped_title = Column(String, nullable=True)
    scraped_description = Column(String, nullable=True)
    scraped_image_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=True)
    scrape_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    list = relationship("ItemList", back_populates="items")
    recipient = relationship("Contact", back_populates="items")
