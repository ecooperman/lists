"""What the dashboard's stats pages ask this app: for each account, when they were last here and how much they keep in it, as numbers
and dates only (never a list's name, an item or a price). Administrators only."""
from fastapi import APIRouter, Depends
from shared_python import usage
from sqlalchemy.orm import Session

from .. import models
from ..auth import require_admin
from ..deps import get_db

router = APIRouter(prefix="/api/admin/stats", tags=["stats"], dependencies=[Depends(require_admin)])

_ITEMS_OF_OWNER = models.ItemList.__table__.join(models.Item.__table__, models.Item.list_id == models.ItemList.id)


@router.get("")
def stats(db: Session = Depends(get_db)):
    return usage.build(db, models.User, {
        "lists": usage.per_user(db, models.ItemList.owner_id, models.ItemList.created_at),
        "items on their lists": usage.per_user(db, models.ItemList.owner_id, models.Item.created_at, source=_ITEMS_OF_OWNER),
        "items done": usage.per_user(db, models.ItemList.owner_id, models.Item.done_at, models.Item.done.is_(True), source=_ITEMS_OF_OWNER),
        "lists shared with them": usage.per_user(db, models.ListMember.user_id, None, models.ListMember.role != models.ROLE_OWNER),
        "contacts": usage.per_user(db, models.Contact.owner_id),
        "copies emailed": usage.per_user(db, models.CopyEmail.user_id, models.CopyEmail.sent_at),
    })
