from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

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


class GiftBase(BaseModel):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    needed_by: Optional[datetime] = None
    recipient_id: Optional[int] = None


class GiftCreate(GiftBase):
    pass


class GiftUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    needed_by: Optional[datetime] = None
    recipient_id: Optional[int] = None
    purchased: Optional[bool] = None


class Gift(GiftBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchased: bool
    purchased_at: Optional[datetime] = None
    recipient: Optional[Contact] = None
    scrape_status: ScrapeStatus
    scraped_title: Optional[str] = None
    scraped_description: Optional[str] = None
    scraped_image_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
