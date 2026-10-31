from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=List[schemas.Category])
def list_categories(db: Session = Depends(get_db)):
    return crud.get_categories(db)


@router.post("", response_model=schemas.Category)
def create_category(category: schemas.CategoryCreate, db: Session = Depends(get_db)):
    if crud.category_name_taken(db, category.name):
        raise HTTPException(status_code=409, detail="A category with that name already exists")
    return crud.create_category(db, category)


@router.post("/reorder", response_model=List[schemas.Category])
def reorder_categories(body: schemas.CategoryReorderRequest, db: Session = Depends(get_db)):
    return crud.reorder_categories(db, body.ordered_ids)


@router.patch("/{category_id}", response_model=schemas.Category)
def update_category(category_id: int, updates: schemas.CategoryUpdate, db: Session = Depends(get_db)):
    if updates.name is not None and crud.category_name_taken(db, updates.name, exclude_id=category_id):
        raise HTTPException(status_code=409, detail="A category with that name already exists")
    category = crud.update_category(db, category_id, updates)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    result = crud.delete_category(db, category_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Category not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Category still has lists assigned to it")
    return {"ok": True}
