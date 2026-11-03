import re
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, notify, schemas
from ..access import check_role, list_access
from ..auth import current_user, is_admin
from ..deps import get_db
from ..importer import parse_dash_list
from .invites import approve

router = APIRouter(prefix="/api/lists", tags=["lists"])

# What a PATCH on a list may change, by who may change it. Everything else is
# the list as everyone sees it; category_id is only this person's own filing.
OWNER_FIELDS = {"name", "purpose", "locked", "priority_labels"}
EDITOR_FIELDS = {"sort_mode"}
PERSONAL_FIELDS = {"category_id"}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("", response_model=List[schemas.ItemList])
def list_lists(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crud.get_lists(db, user.id)


@router.post("", response_model=schemas.ItemList)
def create_list(item_list: schemas.ItemListCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crud.create_list(db, user, item_list)


@router.put("/order", response_model=List[schemas.ItemList])
def reorder_lists(body: schemas.ListOrderRequest, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if not crud.reorder_lists(db, user.id, body.list_ids):
        raise HTTPException(status_code=400, detail="list_ids must be unique, existing lists")
    return crud.get_lists(db, user.id)


@router.get("/{list_id}", response_model=schemas.ItemList)
def get_list(member: models.ListMember = Depends(list_access(models.ROLE_VIEW)), db: Session = Depends(get_db)):
    return crud.list_view(db, member)


@router.patch("/{list_id}", response_model=schemas.ItemList)
def update_list(
    updates: schemas.ItemListUpdate,
    member: models.ListMember = Depends(list_access(models.ROLE_VIEW)),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    sent = updates.model_fields_set
    if "sort_mode" in sent and updates.sort_mode is None:
        raise HTTPException(status_code=400, detail="sort_mode must be manual or priority")
    if sent & OWNER_FIELDS:
        check_role(member, models.ROLE_OWNER)
    if sent & EDITOR_FIELDS:
        check_role(member, models.ROLE_EDIT)
    if updates.category_id is not None and crud.get_category(db, user.id, updates.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    data = updates.model_dump(exclude_unset=True)
    list_fields = {k: v for k, v in data.items() if k not in PERSONAL_FIELDS}
    member_fields = {k: v for k, v in data.items() if k in PERSONAL_FIELDS}
    return crud.update_list(db, member, list_fields, member_fields)


@router.delete("/{list_id}")
def delete_list(
    force: bool = False,
    member: models.ListMember = Depends(list_access(models.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    result, deleted_items = crud.delete_list(db, member, force)
    if result == "locked":
        raise HTTPException(status_code=409, detail="List is locked - unlock it before deleting it")
    if result == "in_use":
        raise HTTPException(
            status_code=409,
            detail="List still has items in it - move or delete them first, or pass force=true to delete them with the list",
        )
    return {"ok": True, "deleted_items": deleted_items}


# --- who has access ---


def _member_out(member: models.ListMember) -> schemas.Member:
    return schemas.Member(user_id=member.user_id, email=member.user.email, role=member.role)


@router.get("/{list_id}/members", response_model=List[schemas.Member])
def list_members(member: models.ListMember = Depends(list_access(models.ROLE_OWNER)), db: Session = Depends(get_db)):
    return [_member_out(m) for m in crud.get_members(db, member.list_id)]


@router.post("/{list_id}/members", response_model=schemas.Member)
def add_member(
    body: schemas.MemberAdd,
    member: models.ListMember = Depends(list_access(models.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    """Only people who already have an account can be added; someone new has
    to be asked for (POST .../invites) and approved first."""
    email = crud.normalize_email(body.email)
    if not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="That doesn't look like an email address")
    user = crud.get_account(db, email)
    if user is None:
        raise HTTPException(status_code=404, detail="No one with that email has signed in yet")
    added = crud.add_member(db, member.list_id, user, body.role)
    if added is None:
        raise HTTPException(status_code=409, detail="That person already has access to this list")
    return _member_out(crud.get_member(db, member.list_id, added.user_id))


@router.patch("/{list_id}/members/{user_id}", response_model=schemas.Member)
def update_member(
    user_id: int,
    body: schemas.MemberUpdate,
    member: models.ListMember = Depends(list_access(models.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    target = crud.get_member(db, member.list_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="That person isn't on this list")
    if target.role == models.ROLE_OWNER:
        raise HTTPException(status_code=400, detail="The owner's access can't be changed")
    return _member_out(crud.set_member_role(db, target, body.role))


@router.delete("/{list_id}/members/{user_id}")
def remove_member(
    user_id: int,
    member: models.ListMember = Depends(list_access(models.ROLE_VIEW)),
    db: Session = Depends(get_db),
):
    """The owner can remove anyone else; anyone else can remove only
    themselves (leave the list)."""
    if user_id != member.user_id:
        check_role(member, models.ROLE_OWNER)
    target = crud.get_member(db, member.list_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="That person isn't on this list")
    if target.role == models.ROLE_OWNER:
        raise HTTPException(status_code=400, detail="The owner can't be removed - delete the list instead")
    crud.remove_member(db, target)
    return {"ok": True}


# --- asking for someone new to be let in ---


@router.get("/{list_id}/invites", response_model=List[schemas.Invite])
def list_invites(member: models.ListMember = Depends(list_access(models.ROLE_OWNER)), db: Session = Depends(get_db)):
    """This list's requests that are waiting or were declined."""
    return crud.get_list_invites(db, member.list_id)


@router.post("/{list_id}/invites", response_model=schemas.Invite)
def request_invite(
    body: schemas.InviteCreate,
    background: BackgroundTasks,
    member: models.ListMember = Depends(list_access(models.ROLE_OWNER)),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Ask for someone with no account to be let in, with a role on this list.
    The administrator is told and decides; the person is added to the list when
    they approve. An administrator's own request is approved straight away."""
    email = crud.normalize_email(body.email)
    if not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="That doesn't look like an email address")
    if crud.get_account(db, email) is not None:
        raise HTTPException(status_code=409, detail="They already have an account - add them to the list instead")
    invite, problem = crud.create_invite(db, member.list_id, user, email, body.role)
    if problem == "duplicate":
        raise HTTPException(status_code=409, detail="You've already asked for that person on this list")
    if problem == "none_left":
        raise HTTPException(status_code=403, detail="You've used all your invites")
    if is_admin(user):
        return approve(db, invite)
    background.add_task(notify.invite_requested, user.email, invite.email, invite.role)
    return invite


@router.delete("/{list_id}/invites/{invite_id}")
def cancel_invite(
    invite_id: int,
    member: models.ListMember = Depends(list_access(models.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    """Withdraw a request that's still waiting (this gives the invite back)."""
    invite = crud.get_invite(db, invite_id)
    if invite is None or invite.list_id != member.list_id:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != models.INVITE_PENDING:
        raise HTTPException(status_code=409, detail="Only a request that's still waiting can be withdrawn")
    crud.cancel_invite(db, invite)
    return {"ok": True}


# --- items ---


@router.get("/{list_id}/contacts", response_model=List[schemas.ContactRef])
def list_contacts(member: models.ListMember = Depends(list_access(models.ROLE_VIEW)), db: Session = Depends(get_db)):
    """Who an item on this list can be for: its owner's contacts (names only)."""
    return crud.get_list_contacts(db, member.list_id)


@router.get("/{list_id}/items", response_model=List[schemas.Item])
def list_items(member: models.ListMember = Depends(list_access(models.ROLE_VIEW)), db: Session = Depends(get_db)):
    return crud.get_items(db, member.list_id)


@router.post("/{list_id}/items", response_model=schemas.Item)
def create_item(
    item: schemas.ItemCreate,
    member: models.ListMember = Depends(list_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    if item.recipient_id is not None and not crud.contact_usable_for_list(db, item.recipient_id, member.list_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    return crud.create_item(db, member.list_id, item)


@router.put("/{list_id}/items/order", response_model=List[schemas.Item])
def reorder_items(
    body: schemas.ItemOrderRequest,
    member: models.ListMember = Depends(list_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    if not crud.reorder_items(db, member.list_id, body.item_ids):
        raise HTTPException(status_code=400, detail="item_ids must be unique items of this list")
    return crud.get_items(db, member.list_id)


# Import pasted notes as items - one per "-" line. Two steps so the UI can
# show what will be created before anything is saved.
@router.post("/{list_id}/items/import/preview", response_model=List[schemas.ItemImportPreview])
def preview_import(body: schemas.ItemImportRequest, member: models.ListMember = Depends(list_access(models.ROLE_EDIT))):
    return [schemas.ItemImportPreview(name=name) for name in parse_dash_list(body.text)]


@router.post("/{list_id}/items/import", response_model=List[schemas.Item])
def import_items(
    body: schemas.ItemImportRequest,
    member: models.ListMember = Depends(list_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    names = parse_dash_list(body.text)
    if not names:
        raise HTTPException(status_code=400, detail="No items found - start each item on its own line with a dash")
    return crud.create_items(db, member.list_id, names)
