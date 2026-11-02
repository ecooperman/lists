"""Per-list access checks, as FastAPI dependencies.

A person who isn't a member of a list gets the same 404 as for a list that
doesn't exist, so ids can't be probed. A member without enough access gets a
403 saying what they can do instead.
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException

from . import crud, models
from .auth import current_user
from .deps import get_db


def check_role(member: models.ListMember, minimum: str) -> None:
    if models.ROLE_RANK[member.role] >= models.ROLE_RANK[minimum]:
        return
    if minimum == models.ROLE_OWNER:
        raise HTTPException(status_code=403, detail="Only the list's owner can do that")
    raise HTTPException(status_code=403, detail="You have view-only access to this list")


def list_access(minimum: str):
    """Dependency for routes with a {list_id} path parameter: the caller's
    membership of that list, requiring at least `minimum` role."""

    def dependency(list_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> models.ListMember:
        member = crud.get_membership(db, user.id, list_id)
        if member is None:
            raise HTTPException(status_code=404, detail="List not found")
        check_role(member, minimum)
        return member

    return dependency


@dataclass
class ItemAccess:
    item: models.Item
    member: models.ListMember


def item_access(minimum: str):
    """Same for routes with an {item_id}: access is whatever the caller has on
    the item's list."""

    def dependency(item_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> ItemAccess:
        item = crud.get_item(db, item_id)
        member = crud.get_membership(db, user.id, item.list_id) if item is not None else None
        if item is None or member is None:
            raise HTTPException(status_code=404, detail="Item not found")
        check_role(member, minimum)
        return ItemAccess(item=item, member=member)

    return dependency
