from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/lists", tags=["lists"])


@router.get("", response_model=List[schemas.ItemList])
def list_lists(db: Session = Depends(get_db)):
    return crud.get_lists(db)


@router.post("", response_model=schemas.ItemList)
def create_list(item_list: schemas.ItemListCreate, db: Session = Depends(get_db)):
    return crud.create_list(db, item_list)


@router.get("/{list_id}", response_model=schemas.ItemList)
def get_list(list_id: int, db: Session = Depends(get_db)):
    item_list = crud.get_list(db, list_id)
    if item_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return item_list


@router.patch("/{list_id}", response_model=schemas.ItemList)
def update_list(list_id: int, updates: schemas.ItemListUpdate, db: Session = Depends(get_db)):
    item_list = crud.update_list(db, list_id, updates)
    if item_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return item_list


@router.delete("/{list_id}")
def delete_list(list_id: int, db: Session = Depends(get_db)):
    result = crud.delete_list(db, list_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="List not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="List still has items in it - move or delete them first")
    return {"ok": True}


@router.get("/{list_id}/items", response_model=List[schemas.Item])
def list_items(list_id: int, db: Session = Depends(get_db)):
    if crud.get_list(db, list_id) is None:
        raise HTTPException(status_code=404, detail="List not found")
    return crud.get_items(db, list_id)


@router.post("/{list_id}/items", response_model=schemas.Item)
def create_item(list_id: int, item: schemas.ItemCreate, db: Session = Depends(get_db)):
    if crud.get_list(db, list_id) is None:
        raise HTTPException(status_code=404, detail="List not found")
    return crud.create_item(db, list_id, item)
