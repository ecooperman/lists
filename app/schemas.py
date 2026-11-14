from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .models import ScrapeStatus


class ContactBase(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class Contact(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ContactRef(BaseModel):
    """What other people on a shared list see of a recipient: just the name,
    never the address-book details (email, address)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: Optional[str] = None


class Me(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool = False
    # How many more people they may ask to have let in; null = no limit.
    invites_left: Optional[int] = None
    # Requests waiting for approval (administrators only, else 0).
    pending_invites: int = 0


class AdminUser(BaseModel):
    """One person with an account, as the administrator sees them on the Users
    page, with what they own (so deleting them can be confirmed knowingly)."""

    id: int
    email: str
    status: Literal["active", "removed"]
    is_admin: bool
    created_at: Optional[datetime] = None
    owned_lists: int = 0
    # Lists someone else owns that this person is on.
    shared_with_them: int = 0
    # Other people who are on the lists this person owns (deleting those lists removes the lists for them too).
    people_on_their_lists: int = 0
    items: int = 0
    contacts: int = 0
    categories: int = 0


class UserAdd(BaseModel):
    email: str = Field(min_length=3, max_length=254)


# What a category made from a dropdown (name only) looks like until it is
# recoloured on the Categories page: a light neutral grey, which dark text reads on.
DEFAULT_CATEGORY_COLOR = "#cbd5e1"


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(default=DEFAULT_CATEGORY_COLOR, pattern=r"^#[0-9a-fA-F]{6}$")
    text_color: Literal["dark", "light"] = "dark"


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    text_color: Optional[Literal["dark", "light"]] = None


class Category(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int


class CategoryReorderRequest(BaseModel):
    # The full new order as category ids; the server resequences everyone.
    ordered_ids: List[int]


class CopyOptions(BaseModel):
    """What goes into a copy of a list or item (see app/sendcopy.py). The item's
    name is always there; each of these is an optional addition."""

    links: bool = True
    description: bool = False
    needed_by: bool = False
    priority: bool = False
    progress: bool = False
    recipient: bool = False  # the contact's name only, never their email or address
    prices: bool = False  # each item's price (final cost, else estimate) and a total line; lists that track costs
    style: Literal["numbered", "bulleted", "checkboxes", "plain"] = "bulleted"
    done: Literal["show", "hide", "strike"] = "show"
    order: Literal["list", "priority"] = "list"  # "list" = as the list itself shows them
    heading: bool = True  # the list's name above the items (lists only)


class EmailCopyRequest(CopyOptions):
    """Send a copy by email: the same choices, and who gets it (one address)."""

    to: str = Field(min_length=3, max_length=254)


class EmailCopyResult(BaseModel):
    sent_to: str
    left_today: Optional[int] = None  # None = no limit (administrator)


class CopyResult(BaseModel):
    text: str  # plain text, for messages and notes
    html: str  # the rich version, for email and documents
    count: int  # how many items it holds


class LinkLabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class LinkLabelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)


class LinkLabel(LinkLabelCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int


class LinkLabelReorderRequest(BaseModel):
    # The full new order as label ids; the server resequences everyone.
    ordered_ids: List[int]


class ListOrderRequest(BaseModel):
    # List ids in the order they should appear, top first.
    list_ids: List[int]


class ItemListBase(BaseModel):
    name: str
    purpose: Optional[str] = None


class ItemListCreate(ItemListBase):
    pass


SortMode = Literal["manual", "priority", "price"]
PriorityLabel = Annotated[str, StringConstraints(max_length=30)]


class ItemListUpdate(BaseModel):
    name: Optional[str] = None
    purpose: Optional[str] = None
    locked: Optional[bool] = None
    sort_mode: Optional[SortMode] = None
    category_id: Optional[int] = None  # null clears it
    track_costs: Optional[bool] = None
    # Exactly five labels for priority levels 1-5; a blank one falls back to
    # its default, and null resets all five.
    priority_labels: Optional[List[PriorityLabel]] = Field(default=None, min_length=5, max_length=5)
    # Levels (1-5) this list does not offer in its priority pickers; [] shows all five.
    # At least one must stay visible (checked in the router, where the body's shape is known).
    hidden_priorities: Optional[List[Annotated[int, Field(ge=1, le=5)]]] = Field(default=None, max_length=5)


class PriorityCost(BaseModel):
    priority: Optional[int] = None  # 1-5, or null for items with no priority
    total_cents: int


class ItemList(ItemListBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    locked: bool
    sort_mode: SortMode
    priority_labels: List[str]
    hidden_priorities: List[int] = []
    created_at: datetime
    # Not columns - crud.list_views() sets these on each row for the person
    # asking: where *they* have the list (position, category), what they can
    # do with it, and who it's shared with, plus the counts so the lists
    # index can show "N left" without a request per list.
    sort_order: int
    category_id: Optional[int] = None
    my_role: Literal["owner", "edit", "view"]
    owner_email: str
    member_count: int = 1
    item_count: int = 0
    open_count: int = 0
    # Only meaningful when track_costs is on (else 0): what the items add up to, counting each at
    # its final cost or, failing that, its estimate; how much of that is already bought (done items);
    # and how many items have no price at all yet.
    track_costs: bool = False
    cost_total_cents: int = 0
    cost_bought_cents: int = 0
    unpriced_count: int = 0
    # cost_total_cents split by priority level, highest level first (null = no priority last);
    # levels that add up to nothing are left out, so these always sum to cost_total_cents.
    cost_by_priority: List[PriorityCost] = []


class Member(BaseModel):
    user_id: int
    email: str
    role: Literal["owner", "edit", "view"]


class MemberAdd(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["edit", "view"]


class MemberUpdate(BaseModel):
    role: Literal["edit", "view"]


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["edit", "view"]


class Invite(BaseModel):
    """A request for someone without an account, as its inviter sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: Literal["edit", "view"]
    status: Literal["pending", "approved", "declined"]
    created_at: datetime


class AppInviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class AppInvite(BaseModel):
    """A request to let someone into the app itself, as its asker sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    status: Literal["pending", "approved", "declined"]
    created_at: datetime


class AdminInvite(Invite):
    """The same request as the administrator sees it, with who and what for."""

    invited_by_email: str
    # True when it is to the app itself rather than to one list.
    for_app: bool = False
    # When it was decided (set for declined requests).
    decided_at: Optional[datetime] = None
    list_name: Optional[str] = None


MAX_LINKS_PER_ITEM = 20


class ItemLinkIn(BaseModel):
    """A link as it is sent: what it is (optional) and where it goes."""

    label: Optional[str] = Field(default=None, max_length=40)
    url: str = Field(max_length=2000)

    @field_validator("label")
    @classmethod
    def _clean_label(cls, value):
        value = (value or "").strip()
        return value or None

    @field_validator("url")
    @classmethod
    def _web_address_only(cls, value):
        value = value.strip()
        # Only web pages: these end up as clickable addresses for everyone the
        # list is shared with, so javascript: and the like are refused outright.
        if not value.lower().startswith(("http://", "https://")) or len(value) <= len("https://"):
            raise ValueError("A link must be a web address starting with http:// or https://")
        return value


class ItemLink(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: Optional[str] = None
    url: str


# Money is whole cents (up to $10 million, which no list here comes near).
Cents = Annotated[int, Field(ge=0, le=1_000_000_000)]


class ItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    needed_by: Optional[datetime] = None
    recipient_id: Optional[int] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    estimate_cents: Optional[Cents] = None
    final_cents: Optional[Cents] = None


class ItemCreate(ItemBase):
    links: List[ItemLinkIn] = Field(default_factory=list, max_length=MAX_LINKS_PER_ITEM)


class ItemImportRequest(BaseModel):
    # The pasted notes - one item per "-" line (see app/importer.py).
    text: str = Field(max_length=100_000)


class ItemOrderRequest(BaseModel):
    # Item ids in the order they should appear, top first.
    item_ids: List[int]


class ItemImportPreview(BaseModel):
    name: str


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    # The whole set of links, in order: sending it replaces what the item has
    # (an empty list clears them); leaving it out changes nothing.
    links: Optional[List[ItemLinkIn]] = Field(default=None, max_length=MAX_LINKS_PER_ITEM)
    needed_by: Optional[datetime] = None
    recipient_id: Optional[int] = None
    done: Optional[bool] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    priority: Optional[int] = Field(default=None, ge=1, le=5)  # null clears it
    estimate_cents: Optional[Cents] = None  # null clears it
    final_cents: Optional[Cents] = None  # null clears it (the estimate counts again)
    # Moves the item to another list. Can't be cleared - every item belongs
    # to exactly one list (the router rejects an explicit null).
    list_id: Optional[int] = None


class Item(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    list_id: int
    links: List[ItemLink] = []
    # The first link's address (null if there are none): what older callers
    # of this API knew as the item's one url. Read-only.
    url: Optional[str] = None
    done: bool
    done_at: Optional[datetime] = None
    progress: int
    # What the item counts as in a cost total: the final cost if entered, else the estimate (null: neither).
    cost_cents: Optional[int] = None
    recipient: Optional[ContactRef] = None
    scrape_status: ScrapeStatus
    scraped_title: Optional[str] = None
    scraped_description: Optional[str] = None
    scraped_image_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
