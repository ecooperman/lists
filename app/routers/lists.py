from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..importer import parse_dash_list
from ..deps import get_db

router = APIRouter(prefix="/api/lists", tags=["lists"])


@router.get("", response_model=List[schemas.ItemList])
def list_lists(db: Session = Depends(get_db)):
    return crud.get_lists(db)


@router.post("", response_model=schemas.ItemList)
def create_list(item_list: schemas.ItemListCreate, db: Session = Depends(get_db)):
    return crud.create_list(db, item_list)


@router.put("/order", response_model=List[schemas.ItemList])
def reorder_lists(body: schemas.ListOrderRequest, db: Session = Depends(get_db)):
    if not crud.reorder_lists(db, body.list_ids):
        raise HTTPException(status_code=400, detail="list_ids must be unique, existing lists")
    return crud.get_lists(db)


@router.get("/{list_id}", response_model=schemas.ItemList)
def get_list(list_id: int, db: Session = Depends(get_db)):
    item_list = crud.get_list(db, list_id)
    if item_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return item_list


@router.patch("/{list_id}", response_model=schemas.ItemList)
def update_list(list_id: int, updates: schemas.ItemListUpdate, db: Session = Depends(get_db)):
    if "sort_mode" in updates.model_fields_set and updates.sort_mode is None:
        raise HTTPException(status_code=400, detail="sort_mode must be manual or priority")
    if updates.category_id is not None and crud.get_category(db, updates.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    item_list = crud.update_list(db, list_id, updates)
    if item_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return item_list


@router.delete("/{list_id}")
def delete_list(list_id: int, force: bool = False, db: Session = Depends(get_db)):
    result, deleted_items = crud.delete_list(db, list_id, force)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="List not found")
    if result == "locked":
        raise HTTPException(status_code=409, detail="List is locked - unlock it before deleting it")
    if result == "in_use":
        raise HTTPException(
            status_code=409,
            detail="List still has items in it - move or delete them first, or pass force=true to delete them with the list",
        )
    return {"ok": True, "deleted_items": deleted_items}


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


@router.put("/{list_id}/items/order", response_model=List[schemas.Item])
def reorder_items(list_id: int, body: schemas.ItemOrderRequest, db: Session = Depends(get_db)):
    if crud.get_list(db, list_id) is None:
        raise HTTPException(status_code=404, detail="List not found")
    if not crud.reorder_items(db, list_id, body.item_ids):
        raise HTTPException(status_code=400, detail="item_ids must be unique items of this list")
    return crud.get_items(db, list_id)


# Import pasted notes as items - one per "-" line. Two steps so the UI can
# show what will be created before anything is saved.
@router.post("/{list_id}/items/import/preview", response_model=List[schemas.ItemImportPreview])
def preview_import(list_id: int, body: schemas.ItemImportRequest, db: Session = Depends(get_db)):
    if crud.get_list(db, list_id) is None:
        raise HTTPException(status_code=404, detail="List not found")
    return [schemas.ItemImportPreview(name=name) for name in parse_dash_list(body.text)]


@router.post("/{list_id}/items/import", response_model=List[schemas.Item])
def import_items(list_id: int, body: schemas.ItemImportRequest, db: Session = Depends(get_db)):
    if crud.get_list(db, list_id) is None:
        raise HTTPException(status_code=404, detail="List not found")
    names = parse_dash_list(body.text)
    if not names:
        raise HTTPException(status_code=400, detail="No items found - start each item on its own line with a dash")
    return crud.create_items(db, list_id, names)
