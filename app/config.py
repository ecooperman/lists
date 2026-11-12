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
# Cloudflare Access authenticates everyone before a request reaches the app, and
# shared_python.auth verifies the signed token it attaches. CF_TEAM_DOMAIN and
# CF_ACCESS_AUD come from the shared secrets file (see shared_python/settings.py
# and DEPLOYMENT.md), not from here.

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

# How many copies of lists each person may email in any 24 hours (administrators
# are unlimited). Emailing a copy needs no approval and can go to anyone, so
# this is what stops the app being used to send people mail from our address.
COPY_EMAILS_PER_DAY = _int_env("COPY_EMAILS_PER_DAY", 10)

# --- links in what we send (see app/notify.py) ------------------------------
# The Cloudflare group, ntfy/Pushover and email settings are shared by every app
# (shared_python/settings.py); only where this app lives is its own.
PUBLIC_URL = "https://lists.evancooperman.com" if ENV == "production" else f"http://{HOST}:{PORT}"
