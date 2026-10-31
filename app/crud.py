from datetime import datetime
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


# --- categories ---


def get_categories(db: Session):
    return db.query(models.Category).order_by(models.Category.sort_order, models.Category.id).all()


def get_category(db: Session, category_id: int):
    return db.query(models.Category).filter(models.Category.id == category_id).first()


def category_name_taken(db: Session, name: str, exclude_id: Optional[int] = None) -> bool:
    query = db.query(models.Category).filter(func.lower(models.Category.name) == name.strip().lower())
    if exclude_id is not None:
        query = query.filter(models.Category.id != exclude_id)
    return query.first() is not None


def create_category(db: Session, category: schemas.CategoryCreate):
    # Appended to the end with gaps (max+10), same as trip-planning's.
    top = db.query(func.max(models.Category.sort_order)).scalar() or 0
    data = category.model_dump()
    data["name"] = data["name"].strip()
    db_category = models.Category(**data, sort_order=top + 10)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def update_category(db: Session, category_id: int, updates: schemas.CategoryUpdate):
    db_category = get_category(db, category_id)
    if db_category is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_category, field, value.strip() if field == "name" and value else value)
    db.commit()
    db.refresh(db_category)
    return db_category


def reorder_categories(db: Session, ordered_ids):
    by_id = {c.id: c for c in db.query(models.Category).filter(models.Category.id.in_(ordered_ids))}
    for index, category_id in enumerate(ordered_ids):
        if category_id in by_id:  # a stale id (deleted elsewhere) is skipped, not an error
            by_id[category_id].sort_order = (index + 1) * 10
    db.commit()
    return get_categories(db)


def delete_category(db: Session, category_id: int) -> str:
    db_category = get_category(db, category_id)
    if db_category is None:
        return "not_found"
    # Same guard as contacts: never silently orphan lists.
    if db.query(models.ItemList).filter(models.ItemList.category_id == category_id).first() is not None:
        return "in_use"
    db.delete(db_category)
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
    rows = db.query(models.ItemList).order_by(models.ItemList.sort_order, models.ItemList.id).all()
    return attach_counts(db, rows)


def get_list(db: Session, list_id: int):
    row = db.query(models.ItemList).filter(models.ItemList.id == list_id).first()
    if row is not None:
        attach_counts(db, [row])
    return row


def _next_list_order(db: Session) -> int:
    top = db.query(func.max(models.ItemList.sort_order)).scalar()
    return 0 if top is None else top + 1


def reorder_lists(db: Session, list_ids) -> bool:
    """Give the listed lists positions 0..n-1 in the order given. False (and
    nothing changed) if an id repeats or isn't a list."""
    if len(set(list_ids)) != len(list_ids):
        return False
    rows = {row.id: row for row in db.query(models.ItemList).filter(models.ItemList.id.in_(list_ids))}
    if len(rows) != len(list_ids):
        return False
    for position, list_id in enumerate(list_ids):
        rows[list_id].sort_order = position
    db.commit()
    return True


def create_list(db: Session, item_list: schemas.ItemListCreate):
    db_list = models.ItemList(sort_order=_next_list_order(db), **item_list.model_dump())
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
    sort_mode = db.query(models.ItemList.sort_mode).filter(models.ItemList.id == list_id).scalar()
    # Done items always sink to the bottom. Within each group: the list's own
    # manual order, or - in priority mode - highest priority first with ties
    # kept in manual order (id only breaks exact sort_order ties).
    order = [models.Item.done]
    if sort_mode == "priority":
        order.append(models.Item.priority.desc().nulls_last())
    order += [models.Item.sort_order, models.Item.id]
    return (
        db.query(models.Item)
        .options(joinedload(models.Item.recipient))
        .filter(models.Item.list_id == list_id)
        .order_by(*order)
        .all()
    )


def _next_sort_order(db: Session, list_id: int) -> int:
    top = db.query(func.max(models.Item.sort_order)).filter(models.Item.list_id == list_id).scalar()
    return 0 if top is None else top + 1


def get_item(db: Session, item_id: int):
    return (
        db.query(models.Item)
        .options(joinedload(models.Item.recipient))
        .filter(models.Item.id == item_id)
        .first()
    )


def create_item(db: Session, list_id: int, item: schemas.ItemCreate):
    db_item = models.Item(list_id=list_id, sort_order=_next_sort_order(db, list_id), **item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def create_items(db: Session, list_id: int, names) -> list:
    """Create several items in one commit, one per name, appended in order."""
    first = _next_sort_order(db, list_id)
    db_items = [models.Item(list_id=list_id, name=name, sort_order=first + i) for i, name in enumerate(names)]
    db.add_all(db_items)
    db.commit()
    for db_item in db_items:
        db.refresh(db_item)
    return db_items


def reorder_items(db: Session, list_id: int, item_ids) -> bool:
    """Give the listed items positions 0..n-1 in the order given. False (and
    nothing changed) if any id is repeated or isn't an item of this list."""
    if len(set(item_ids)) != len(item_ids):
        return False
    rows = {
        row.id: row
        for row in db.query(models.Item).filter(models.Item.list_id == list_id, models.Item.id.in_(item_ids))
    }
    if len(rows) != len(item_ids):
        return False
    for position, item_id in enumerate(item_ids):
        rows[item_id].sort_order = position
    db.commit()
    return True


def update_item(db: Session, item_id: int, updates: schemas.ItemUpdate):
    db_item = get_item(db, item_id)
    if db_item is None:
        return None
    fields = updates.model_dump(exclude_unset=True)
    if "done" in fields:
        # Track when an item was checked off so the UI can show it, and
        # clear it again if someone un-checks the box.
        db_item.done_at = datetime.utcnow() if fields["done"] else None
    if "list_id" in fields and fields["list_id"] != db_item.list_id:
        # Moved to another list: land at the end of it.
        db_item.sort_order = _next_sort_order(db, fields["list_id"])
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
