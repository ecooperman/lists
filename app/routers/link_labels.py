from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import current_user
from ..deps import get_db

# Your own list of labels for the links on items ("Menu", "Reviews", ...), the
# choices in each link's dropdown. Private to you; a link keeps its own copy of
# the text, so nobody else needs access to this list to read it.
router = APIRouter(prefix="/api/link-labels", tags=["link-labels"])

TAKEN = "A link label with that name already exists"


@router.get("", response_model=List[schemas.LinkLabel])
def list_link_labels(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crud.get_link_labels(db, user.id)


@router.post("", response_model=schemas.LinkLabel)
def create_link_label(label: schemas.LinkLabelCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if crud.link_label_name_taken(db, user.id, label.name):
        raise HTTPException(status_code=409, detail=TAKEN)
    return crud.create_link_label(db, user.id, label)


@router.post("/reorder", response_model=List[schemas.LinkLabel])
def reorder_link_labels(
    body: schemas.LinkLabelReorderRequest, user: models.User = Depends(current_user), db: Session = Depends(get_db)
):
    return crud.reorder_link_labels(db, user.id, body.ordered_ids)


@router.patch("/{label_id}", response_model=schemas.LinkLabel)
def update_link_label(
    label_id: int,
    updates: schemas.LinkLabelUpdate,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if updates.name is not None and crud.link_label_name_taken(db, user.id, updates.name, exclude_id=label_id):
        raise HTTPException(status_code=409, detail=TAKEN)
    label = crud.update_link_label(db, user.id, label_id, updates)
    if label is None:
        raise HTTPException(status_code=404, detail="Link label not found")
    return label


@router.delete("/{label_id}")
def delete_link_label(label_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if not crud.delete_link_label(db, user.id, label_id):
        raise HTTPException(status_code=404, detail="Link label not found")
    return {"ok": True}
