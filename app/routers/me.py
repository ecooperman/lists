from fastapi import APIRouter, Depends

from .. import models, schemas
from ..auth import current_user

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=schemas.Me)
def get_me(user: models.User = Depends(current_user)):
    return user
