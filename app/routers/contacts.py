from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("", response_model=List[schemas.Contact])
def list_contacts(db: Session = Depends(get_db)):
    return crud.get_contacts(db)


@router.post("", response_model=schemas.Contact)
def create_contact(contact: schemas.ContactCreate, db: Session = Depends(get_db)):
    return crud.create_contact(db, contact)


@router.patch("/{contact_id}", response_model=schemas.Contact)
def update_contact(contact_id: int, updates: schemas.ContactUpdate, db: Session = Depends(get_db)):
    contact = crud.update_contact(db, contact_id, updates)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.delete("/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    result = crud.delete_contact(db, contact_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Contact not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Contact still has items assigned to them")
    return {"ok": True}
