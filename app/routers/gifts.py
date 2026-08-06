from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db
from ..scraping.service import scrape_gift

router = APIRouter(prefix="/api/gifts", tags=["gifts"])


@router.get("", response_model=List[schemas.Gift])
def list_gifts(db: Session = Depends(get_db)):
    return crud.get_gifts(db)


@router.post("", response_model=schemas.Gift)
def create_gift(gift: schemas.GiftCreate, db: Session = Depends(get_db)):
    return crud.create_gift(db, gift)


@router.get("/{gift_id}", response_model=schemas.Gift)
def get_gift(gift_id: int, db: Session = Depends(get_db)):
    gift = crud.get_gift(db, gift_id)
    if gift is None:
        raise HTTPException(status_code=404, detail="Gift not found")
    return gift


@router.patch("/{gift_id}", response_model=schemas.Gift)
def update_gift(gift_id: int, updates: schemas.GiftUpdate, db: Session = Depends(get_db)):
    gift = crud.update_gift(db, gift_id, updates)
    if gift is None:
        raise HTTPException(status_code=404, detail="Gift not found")
    return gift


@router.delete("/{gift_id}")
def delete_gift(gift_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_gift(db, gift_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Gift not found")
    return {"ok": True}


@router.post("/{gift_id}/scrape", response_model=schemas.Gift)
def trigger_scrape(gift_id: int, db: Session = Depends(get_db)):
    gift = crud.get_gift(db, gift_id)
    if gift is None:
        raise HTTPException(status_code=404, detail="Gift not found")
    if not gift.url:
        raise HTTPException(status_code=400, detail="Gift has no URL to scrape")
    return scrape_gift(db, gift_id, gift.url)
