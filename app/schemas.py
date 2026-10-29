from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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


class ItemListBase(BaseModel):
    name: str
    purpose: Optional[str] = None


class ItemListCreate(ItemListBase):
    pass


SortMode = Literal["manual", "priority"]
PriorityLabel = Annotated[str, StringConstraints(max_length=30)]


class ItemListUpdate(BaseModel):
    name: Optional[str] = None
    purpose: Optional[str] = None
    locked: Optional[bool] = None
    sort_mode: Optional[SortMode] = None
    # Exactly five labels for priority levels 1-5; a blank one falls back to
    # its default, and null resets all five.
    priority_labels: Optional[List[PriorityLabel]] = Field(default=None, min_length=5, max_length=5)


class ItemList(ItemListBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    locked: bool
    sort_mode: SortMode
    priority_labels: List[str]
    created_at: datetime
    # Not columns - crud.attach_counts() sets these on each row so the lists
    # index can show "N left" without a request per list.
    item_count: int = 0
    open_count: int = 0


class ItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    needed_by: Optional[datetime] = None
    recipient_id: Optional[int] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)


class ItemCreate(ItemBase):
    pass


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
    url: Optional[str] = None
    needed_by: Optional[datetime] = None
    recipient_id: Optional[int] = None
    done: Optional[bool] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    priority: Optional[int] = Field(default=None, ge=1, le=5)  # null clears it
    # Moves the item to another list. Can't be cleared - every item belongs
    # to exactly one list (the router rejects an explicit null).
    list_id: Optional[int] = None


class Item(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    list_id: int
    done: bool
    done_at: Optional[datetime] = None
    progress: int
    recipient: Optional[Contact] = None
    scrape_status: ScrapeStatus
    scraped_title: Optional[str] = None
    scraped_description: Optional[str] = None
    scraped_image_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
