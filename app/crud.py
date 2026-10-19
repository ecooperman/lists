from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, func
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
    still_in_use = db.query(models.Item).filter(models.Item.recipient_id == contact_id).first()
    if still_in_use is not None:
        return "in_use"
    db.delete(db_contact)
    db.commit()
    return "ok"


# --- lists ---


def attach_counts(db: Session, lists):
    """Set item_count/open_count on each list (see schemas.ItemList)."""
    counts = {
        list_id: (total, open_)
        for list_id, total, open_ in db.query(
            models.Item.list_id,
            func.count(models.Item.id),
            func.coalesce(func.sum(case((models.Item.done.is_(False), 1), else_=0)), 0),
        ).group_by(models.Item.list_id)
    }
    for item_list in lists:
        item_list.item_count, item_list.open_count = counts.get(item_list.id, (0, 0))
    return lists


def get_lists(db: Session):
    rows = db.query(models.ItemList).order_by(models.ItemList.name).all()
    return attach_counts(db, rows)


def get_list(db: Session, list_id: int):
    row = db.query(models.ItemList).filter(models.ItemList.id == list_id).first()
    if row is not None:
        attach_counts(db, [row])
    return row


def create_list(db: Session, item_list: schemas.ItemListCreate):
    db_list = models.ItemList(**item_list.model_dump())
    db.add(db_list)
    db.commit()
    db.refresh(db_list)
    return attach_counts(db, [db_list])[0]


def update_list(db: Session, list_id: int, updates: schemas.ItemListUpdate):
    db_list = get_list(db, list_id)
    if db_list is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_list, field, value)
    db.commit()
    db.refresh(db_list)
    return attach_counts(db, [db_list])[0]


def delete_list(db: Session, list_id: int, force: bool = False):
    """Returns (result, deleted_item_count). A locked list is always refused
    ("locked"), force or not - unlock it first. A non-empty list is refused
    ("in_use", same guard as delete_contact) unless force=True, which deletes
    its items along with it - callers should only pass that after the user
    has been told how many items are about to go."""
    db_list = get_list(db, list_id)
    if db_list is None:
        return "not_found", 0
    if db_list.locked:
        return "locked", 0
    if db_list.item_count and not force:
        return "in_use", 0
    deleted = db.query(models.Item).filter(models.Item.list_id == list_id).delete()
    db.delete(db_list)
    db.commit()
    return "ok", deleted


# --- items ---


def get_items(db: Session, list_id: int):
    return (
        db.query(models.Item)
        .options(joinedload(models.Item.recipient))
        .filter(models.Item.list_id == list_id)
        .order_by(
            models.Item.done,
            models.Item.needed_by.is_(None),
            models.Item.needed_by,
            models.Item.created_at.desc(),
        )
        .all()
    )


def get_item(db: Session, item_id: int):
    return (
        db.query(models.Item)
        .options(joinedload(models.Item.recipient))
        .filter(models.Item.id == item_id)
        .first()
    )


def create_item(db: Session, list_id: int, item: schemas.ItemCreate):
    db_item = models.Item(list_id=list_id, **item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def create_items(db: Session, list_id: int, names) -> list:
    """Create several items in one commit, one per name."""
    # The list shows newest-first, so stamp the first pasted line as the
    # newest - otherwise a pasted list would display upside down.
    now = datetime.utcnow()
    db_items = [
        models.Item(list_id=list_id, name=name, created_at=now - timedelta(microseconds=i))
        for i, name in enumerate(names)
    ]
    db.add_all(db_items)
    db.commit()
    for db_item in db_items:
        db.refresh(db_item)
    return db_items


def update_item(db: Session, item_id: int, updates: schemas.ItemUpdate):
    db_item = get_item(db, item_id)
    if db_item is None:
        return None
    fields = updates.model_dump(exclude_unset=True)
    if "done" in fields:
        # Track when an item was checked off so the UI can show it, and
        # clear it again if someone un-checks the box.
        db_item.done_at = datetime.utcnow() if fields["done"] else None
    for field, value in fields.items():
        setattr(db_item, field, value)
    db.commit()
    db.refresh(db_item)
    return db_item


def delete_item(db: Session, item_id: int) -> bool:
    db_item = get_item(db, item_id)
    if db_item is None:
        return False
    db.delete(db_item)
    db.commit()
    return True


def save_scrape_result(
    db: Session,
    item_id: int,
    status: models.ScrapeStatus,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    error: Optional[str] = None,
):
    db_item = get_item(db, item_id)
    if db_item is None:
        return None
    db_item.scrape_status = status
    db_item.scraped_title = title
    db_item.scraped_description = description
    db_item.scraped_image_url = image_url
    db_item.scrape_error = error
    db_item.scraped_at = datetime.utcnow()
    db.commit()
    db.refresh(db_item)
    return db_item
