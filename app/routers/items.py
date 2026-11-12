from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas, sendcopy
from ..access import ItemAccess, check_role, item_access
from ..auth import current_user
from ..deps import get_db
from ..scraping.service import scrape_item

# Listing and creating items live under /api/lists/{list_id}/items (see
# routers/lists.py); this router is for acting on one existing item. Access to
# an item is whatever the caller has on its list.
router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("/{item_id}", response_model=schemas.Item)
def get_item(access: ItemAccess = Depends(item_access(models.ROLE_VIEW))):
    return access.item


@router.patch("/{item_id}", response_model=schemas.Item)
def update_item(
    updates: schemas.ItemUpdate,
    access: ItemAccess = Depends(item_access(models.ROLE_EDIT)),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if "progress" in updates.model_fields_set and updates.progress is None:
        raise HTTPException(status_code=400, detail="Progress must be a number from 0 to 100")
    target_list_id = access.item.list_id
    if "list_id" in updates.model_fields_set:
        if updates.list_id is None:
            raise HTTPException(status_code=400, detail="An item must belong to a list")
        # Moving needs edit access to the destination too.
        destination = crud.get_membership(db, user.id, updates.list_id)
        if destination is None:
            raise HTTPException(status_code=404, detail="List not found")
        check_role(destination, models.ROLE_EDIT)
        target_list_id = updates.list_id
    if updates.recipient_id is not None and not crud.contact_usable_for_list(db, updates.recipient_id, target_list_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    return crud.update_item(db, access.item, updates)


@router.post("/{item_id}/copy", response_model=schemas.CopyResult)
def copy_item(options: schemas.CopyOptions, access: ItemAccess = Depends(item_access(models.ROLE_VIEW))):
    """Just this item as a copy to paste elsewhere (no list heading)."""
    return sendcopy.render(None, [access.item], options, access.member.list.priority_labels)


@router.delete("/{item_id}")
def delete_item(access: ItemAccess = Depends(item_access(models.ROLE_EDIT)), db: Session = Depends(get_db)):
    crud.delete_item(db, access.item)
    return {"ok": True}


@router.post("/{item_id}/scrape", response_model=schemas.Item)
def trigger_scrape(access: ItemAccess = Depends(item_access(models.ROLE_EDIT)), db: Session = Depends(get_db)):
    if not access.item.url:
        raise HTTPException(status_code=400, detail="Item has no URL to scrape")
    return scrape_item(db, access.item.id, access.item.url)
