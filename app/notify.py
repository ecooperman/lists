"""Telling people things - the sending lives in shared_python.notify; this is
where Lists' own wording and links go."""
from typing import Optional

from shared_python import notify as shared
from shared_python.notify import describe_failure, notify, send_email  # noqa: F401 - re-exported

from . import config

APP_NAME = "Lists"


def invite_requested(inviter_email: str, invitee_email: str, role: Optional[str] = None) -> None:
    """Tell the administrator a list's owner asked for someone to be let in."""
    shared.invite_requested(APP_NAME, inviter_email, invitee_email, role, f"{config.PUBLIC_URL}/invites.html")


def tell_given_access(
    to: str, inviter_email: str, list_name: str, list_id: Optional[int], role: str, new_person: bool
) -> None:
    """Email someone that they've been given access to a list."""
    url = f"{config.PUBLIC_URL}/list.html?id={list_id}" if list_id is not None else None
    shared.tell_given_access(to, inviter_email, "list", list_name, url, role, new_person, APP_NAME)


def tell_let_in(to: str, inviter_email: str) -> None:
    """Email someone that they've been let into the app itself (nothing shared yet)."""
    shared.tell_let_in(to, inviter_email, APP_NAME, config.PUBLIC_URL)
