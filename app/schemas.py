from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

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


class ItemListUpdate(BaseModel):
    name: Optional[str] = None
    purpose: Optional[str] = None
    locked: Optional[bool] = None


class ItemList(ItemListBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    locked: bool
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


class ItemCreate(ItemBase):
    pass


class ItemImportRequest(BaseModel):
    # The pasted notes - one item per "-" line (see app/importer.py).
    text: str = Field(max_length=100_000)


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
