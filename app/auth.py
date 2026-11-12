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


NO_ACCESS = {
    "none": "You haven't been given access to Lists. Ask the person who told you about it, or the administrator, to invite you.",
    "removed": "Your access to Lists has been removed. Ask the administrator if you think that's a mistake.",
}


def signed_in_email(request: Request) -> str:
    """The signed-in person's normalized email (401 if there isn't one)."""
    email = crud.normalize_email(request_email(request))
    if "@" not in email:
        raise HTTPException(status_code=401, detail="Not signed in")
    return email


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    """Whoever is asking, who must also have been enabled in this app: getting
    through Cloudflare's login gate (shared with other apps) is not enough."""
    user, problem = crud.user_for_request(db, signed_in_email(request))
    if user is None:
        raise HTTPException(status_code=403, detail=NO_ACCESS[problem])
    return user


def is_admin(user: models.User) -> bool:
    return user.email in config.ADMIN_EMAILS


def require_admin(user: models.User = Depends(current_user)) -> models.User:
    """For what only the app's administrator may do (approving invites)."""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Only the app's administrator can do that")
    return user
