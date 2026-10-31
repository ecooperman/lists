import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
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


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True)
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

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=False)
    text_color = Column(String, nullable=False, default="dark", server_default="dark")
    # User-controlled order (drag on the Categories page); new rows go to the
    # end at max+10, leaving gaps (same pattern as trip-planning).
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    lists = relationship("ItemList", back_populates="category")


class ItemList(Base):
    """A named list with a purpose ("Gifts", "Movies to watch", ...). Every
    list has the same item structure - see Item - so a list is just a name
    and a purpose wrapped around its own items."""

    __tablename__ = "lists"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    purpose = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    # Manual position on the lists index, lower first (see crud.reorder_lists).
    # New lists go to the end.
    sort_order = Column(Integer, nullable=False, default=0)
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
    category = relationship("Category", back_populates="lists")

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
