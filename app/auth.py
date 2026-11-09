"""Who is making this request.

There are no passwords or sign-up forms: every request has already been
through Cloudflare Access, which attaches the signed-in person's email.
shared_python.auth verifies it (and refuses everything in production if that
isn't configured); here it becomes this app's own User row, created the first
time we see them.
"""
import logging

from fastapi import Depends, HTTPException, Request
from shared_python import auth as cloudflare_access
from sqlalchemy.orm import Session

from . import config, crud, models
from .deps import get_db

log = logging.getLogger(__name__)


def request_email(request: Request) -> str:
    """The verified email of whoever is asking (see shared_python/auth.py)."""
    return cloudflare_access.request_email(request, config.DEV_USER_EMAIL)


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    email = crud.normalize_email(request_email(request))
    if "@" not in email:
        raise HTTPException(status_code=401, detail="Not signed in")
    return crud.get_or_create_user(db, email)


def is_admin(user: models.User) -> bool:
    return user.email in config.ADMIN_EMAILS


def require_admin(user: models.User = Depends(current_user)) -> models.User:
    """For what only the app's administrator may do (approving invites)."""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Only the app's administrator can do that")
    return user
