from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import current_user
from ..deps import get_db

# Your own address book. A list you own offers these as who its items are for;
# a list shared with you offers its owner's instead (GET /api/lists/{id}/contacts).
router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("", response_model=List[schemas.Contact])
def list_contacts(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crud.get_contacts(db, user.id)


@router.post("", response_model=schemas.Contact)
def create_contact(contact: schemas.ContactCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crud.create_contact(db, user.id, contact)


@router.patch("/{contact_id}", response_model=schemas.Contact)
def update_contact(
    contact_id: int,
    updates: schemas.ContactUpdate,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    contact = crud.update_contact(db, user.id, contact_id, updates)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.delete("/{contact_id}")
def delete_contact(contact_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    result = crud.delete_contact(db, user.id, contact_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Contact not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Contact still has items assigned to them")
    return {"ok": True}
