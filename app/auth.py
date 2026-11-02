"""Who is making this request.

There are no passwords or sign-up forms: every request has already been
through Cloudflare Access, which attaches the signed-in person's email (as a
signed token, Cf-Access-Jwt-Assertion, and as a plain header). We read it,
and create that person's User row the first time we see them.

Production verifies the token's signature and audience against Cloudflare's
published keys (needs CF_TEAM_DOMAIN + CF_ACCESS_AUD, see config.py); without
them it falls back to the plain header, which is only safe because the app
listens on 127.0.0.1 and so can only be reached through the tunnel.
"""
import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config, crud, models
from .deps import get_db

log = logging.getLogger(__name__)

EMAIL_HEADER = "cf-access-authenticated-user-email"
JWT_HEADER = "cf-access-jwt-assertion"

_jwks_client: Optional[jwt.PyJWKClient] = None
_warned_unverified = False


def _signing_key(token: str):
    """Cloudflare's public key for this token (cached by PyJWKClient)."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(f"https://{config.CF_TEAM_DOMAIN}/cdn-cgi/access/certs", lifespan=3600)
    return _jwks_client.get_signing_key_from_jwt(token).key


def _email_from_verified_token(token: str) -> str:
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=["RS256"],
            audience=config.CF_ACCESS_AUD,
            options={"require": ["exp", "aud"]},
        )
    except jwt.PyJWTError as exc:
        log.warning("Rejected Cloudflare Access token: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid sign-in token")
    email = claims.get("email")
    if not email:
        # e.g. a service token - it identifies a machine, not a person.
        raise HTTPException(status_code=401, detail="Sign-in token has no email")
    return email


def request_email(request: Request) -> str:
    global _warned_unverified
    headers = request.headers
    if config.ENV == "production":
        if config.CF_TEAM_DOMAIN and config.CF_ACCESS_AUD:
            token = headers.get(JWT_HEADER)
            if not token:
                raise HTTPException(status_code=401, detail="Not signed in")
            return _email_from_verified_token(token)
        if not _warned_unverified:
            log.warning("CF_TEAM_DOMAIN/CF_ACCESS_AUD are not set - trusting the Cf-Access-Authenticated-User-Email header unverified")
            _warned_unverified = True
        email = headers.get(EMAIL_HEADER)
        if not email:
            raise HTTPException(status_code=401, detail="Not signed in")
        return email
    # Local development: no Cloudflare, so a header or a `dev_user` cookie (set
    # it in the browser console: document.cookie = "dev_user=bob@example.com;
    # path=/") plays a second person; otherwise the configured dev user.
    return headers.get(EMAIL_HEADER) or request.cookies.get("dev_user") or config.DEV_USER_EMAIL


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    email = crud.normalize_email(request_email(request))
    if "@" not in email:
        raise HTTPException(status_code=401, detail="Not signed in")
    return crud.get_or_create_user(db, email)
