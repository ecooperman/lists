from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db
from ..scraping.service import scrape_item

# Listing and creating items live under /api/lists/{list_id}/items (see
# routers/lists.py); this router is for acting on one existing item.
router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("/{item_id}", response_model=schemas.Item)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = crud.get_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/{item_id}", response_model=schemas.Item)
def update_item(item_id: int, updates: schemas.ItemUpdate, db: Session = Depends(get_db)):
    if "list_id" in updates.model_fields_set:
        if updates.list_id is None:
            raise HTTPException(status_code=400, detail="An item must belong to a list")
        if crud.get_list(db, updates.list_id) is None:
            raise HTTPException(status_code=404, detail="List not found")
    item = crud.update_item(db, item_id, updates)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_item(db, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


@router.post("/{item_id}/scrape", response_model=schemas.Item)
def trigger_scrape(item_id: int, db: Session = Depends(get_db)):
    item = crud.get_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if not item.url:
        raise HTTPException(status_code=400, detail="Item has no URL to scrape")
    return scrape_item(db, item_id, item.url)
