import os

HOST = "127.0.0.1"
PORT = 8030

# "local" (default, for `uvicorn app.main:app --reload` on a dev machine) or
# "production" (set once, droplet-wide, via systemd's DefaultEnvironment -
# see DEPLOYMENT.md - so every app inherits it with no per-service config).
# Drives which shared-assets host the app's templates point at, so
# switching between local iteration and the real deploy never means
# hand-editing a URL and remembering to revert it.
ENV = os.environ.get("APP_ENV", "local")
SHARED_ASSETS_BASE = "https://static.evancooperman.com" if ENV == "production" else "http://127.0.0.1:8070"

# --- who is signed in (see app/auth.py) -------------------------------------
# There is no login form: Cloudflare Access authenticates everyone before a
# request reaches the app and tells us who it was. In production the app
# verifies the signed token Access attaches (REQUIRED in production - the app
# refuses every request without both values; needs both values below, from
# Zero Trust -> Access -> Applications; the AUD tag is on the application's
# overview page; several, comma-separated, if more than one Access application
# can front this app - each application has its own tag). They live in the shared secrets file every app reads
# (/etc/personal-apps/shared.env, see DEPLOYMENT.md).
CF_TEAM_DOMAIN = os.environ.get("CF_TEAM_DOMAIN")  # e.g. "yourteam.cloudflareaccess.com"
CF_ACCESS_AUD = os.environ.get("CF_ACCESS_AUD")

# Locally there's no Cloudflare in front, so requests are treated as coming
# from this address (a Cf-Access-Authenticated-User-Email header overrides it,
# which is how a second person is simulated in dev and tests). Never used in
# production.
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev@localhost.test").strip().lower()

# The lists that existed before accounts did are parked on a placeholder user
# by the migration, and the first person to sign in takes them over, so
# everything lands on the owner's account with no manual step. ADMIN_EMAILS
# (comma-separated) narrows that to those emails - set it before inviting
# anyone else. Unset in production, whoever signs in first gets them; locally
# it's DEV_USER_EMAIL.
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
ADOPT_LEGACY_ANY = not ADMIN_EMAILS and ENV == "production"
if ENV != "production":
    ADMIN_EMAILS.add(DEV_USER_EMAIL)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# --- letting new people in (see app/routers/invites.py) ----------------------
# A list's owner can ask for someone who has no account yet to be let in; an
# administrator approves each request, which adds the email to the Cloudflare
# Access group that lets people through the login gate. These settings live in
# the shared secrets file (/etc/personal-apps/shared.env, see DEPLOYMENT.md).
#
# How many people each person may ask for (administrators are unlimited). Every
# request counts unless the person cancels it while it's still waiting.
INVITES_PER_USER = _int_env("INVITES_PER_USER", 5)

# The Cloudflare API token needs only "Access: Organizations, Identity
# Providers, and Groups Write". The group is the one the shared-apps Access
# policy allows (the "Invitees" group). Without these, approving a request
# works locally (the Cloudflare step is skipped) but is refused in production.
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_INVITEES_GROUP_ID = os.environ.get("CF_INVITEES_GROUP_ID")
# Cloudflare's free Access plan allows 50 people; approving past this is refused.
ACCESS_SEAT_CAP = _int_env("ACCESS_SEAT_CAP", 50)

# --- telling the administrator a request is waiting (see app/notify.py) -----
# Each channel is on when its settings are present; use any combination.
PUBLIC_URL = "https://lists.evancooperman.com" if ENV == "production" else f"http://{HOST}:{PORT}"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")  # anyone who knows the topic can read it: make it long and random
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN")  # only for a protected topic
PUSHOVER_APP_TOKEN = os.environ.get("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = _int_env("SMTP_PORT", 587)  # 465 = SSL from the start, anything else = STARTTLS
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")  # where the email goes
