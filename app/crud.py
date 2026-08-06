from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from . import models, schemas


# --- contacts ---


def get_contacts(db: Session):
    return db.query(models.Contact).order_by(models.Contact.first_name, models.Contact.last_name).all()


def get_contact(db: Session, contact_id: int):
    return db.query(models.Contact).filter(models.Contact.id == contact_id).first()


def create_contact(db: Session, contact: schemas.ContactCreate):
    db_contact = models.Contact(**contact.model_dump())
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def update_contact(db: Session, contact_id: int, updates: schemas.ContactUpdate):
    db_contact = get_contact(db, contact_id)
    if db_contact is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_contact, field, value)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def delete_contact(db: Session, contact_id: int) -> str:
    db_contact = get_contact(db, contact_id)
    if db_contact is None:
        return "not_found"
    still_in_use = db.query(models.Gift).filter(models.Gift.recipient_id == contact_id).first()
    if still_in_use is not None:
        return "in_use"
    db.delete(db_contact)
    db.commit()
    return "ok"


# --- gifts ---


def get_gifts(db: Session):
    return (
        db.query(models.Gift)
        .options(joinedload(models.Gift.recipient))
        .order_by(
            models.Gift.purchased,
            models.Gift.needed_by.is_(None),
            models.Gift.needed_by,
            models.Gift.created_at.desc(),
        )
        .all()
    )


def get_gift(db: Session, gift_id: int):
    return (
        db.query(models.Gift)
        .options(joinedload(models.Gift.recipient))
        .filter(models.Gift.id == gift_id)
        .first()
    )


def create_gift(db: Session, gift: schemas.GiftCreate):
    db_gift = models.Gift(**gift.model_dump())
    db.add(db_gift)
    db.commit()
    db.refresh(db_gift)
    return db_gift


def update_gift(db: Session, gift_id: int, updates: schemas.GiftUpdate):
    db_gift = get_gift(db, gift_id)
    if db_gift is None:
        return None
    fields = updates.model_dump(exclude_unset=True)
    if "purchased" in fields:
        # Track when a gift was marked purchased so the UI can show it,
        # and clear it again if someone un-checks the box.
        db_gift.purchased_at = datetime.utcnow() if fields["purchased"] else None
    for field, value in fields.items():
        setattr(db_gift, field, value)
    db.commit()
    db.refresh(db_gift)
    return db_gift


def delete_gift(db: Session, gift_id: int) -> bool:
    db_gift = get_gift(db, gift_id)
    if db_gift is None:
        return False
    db.delete(db_gift)
    db.commit()
    return True


def save_scrape_result(
    db: Session,
    gift_id: int,
    status: models.ScrapeStatus,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    error: Optional[str] = None,
):
    db_gift = get_gift(db, gift_id)
    if db_gift is None:
        return None
    db_gift.scrape_status = status
    db_gift.scraped_title = title
    db_gift.scraped_description = description
    db_gift.scraped_image_url = image_url
    db_gift.scrape_error = error
    db_gift.scraped_at = datetime.utcnow()
    db.commit()
    db.refresh(db_gift)
    return db_gift
