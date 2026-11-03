"""Telling the administrator something needs them, over whichever channels are
set up (see config.py): ntfy and Pushover (phone push) and email. A channel
with no settings is skipped, and one failing never stops the others or the
request that triggered it - this runs after the response is sent.
"""
import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

import requests

from . import config

log = logging.getLogger(__name__)

TIMEOUT = 10


def _ntfy(title: str, message: str, link: Optional[str]) -> None:
    if not config.NTFY_TOPIC:
        return
    payload = {"topic": config.NTFY_TOPIC, "title": title, "message": message}
    if link:
        payload["click"] = link
    headers = {"Authorization": f"Bearer {config.NTFY_TOKEN}"} if config.NTFY_TOKEN else {}
    requests.post(config.NTFY_SERVER, json=payload, headers=headers, timeout=TIMEOUT).raise_for_status()


def _pushover(title: str, message: str, link: Optional[str]) -> None:
    if not (config.PUSHOVER_APP_TOKEN and config.PUSHOVER_USER_KEY):
        return
    data = {"token": config.PUSHOVER_APP_TOKEN, "user": config.PUSHOVER_USER_KEY, "title": title, "message": message}
    if link:
        data["url"] = link
    requests.post("https://api.pushover.net/1/messages.json", data=data, timeout=TIMEOUT).raise_for_status()


def _email(title: str, message: str, link: Optional[str]) -> None:
    if not (config.SMTP_HOST and config.SMTP_FROM and config.NOTIFY_EMAIL):
        return
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = config.SMTP_FROM
    msg["To"] = config.NOTIFY_EMAIL
    msg.set_content(f"{message}\n\n{link}" if link else message)
    if config.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=TIMEOUT)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=TIMEOUT)
    with server:
        if config.SMTP_PORT != 465:
            server.starttls()
        if config.SMTP_USERNAME:
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD or "")
        server.send_message(msg)


CHANNELS = {"ntfy": _ntfy, "pushover": _pushover, "email": _email}


def notify(title: str, message: str, link: Optional[str] = None) -> None:
    for name, send in CHANNELS.items():
        try:
            send(title, message, link)
        except Exception as exc:  # noqa: BLE001 - any failure of one channel must not reach the caller
            # The type only: some libraries put the URL or credentials in the message.
            log.warning("Notification via %s failed: %s", name, type(exc).__name__)


def invite_requested(inviter_email: str, invitee_email: str, role: str) -> None:
    access = "edit" if role == "edit" else "view"
    notify(
        "Lists: invite waiting for approval",
        f"{inviter_email} wants to let {invitee_email} in (can {access}).",
        f"{config.PUBLIC_URL}/invites.html",
    )
