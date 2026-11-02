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
# verifies the signed token Access attaches (needs both values below, from
# Zero Trust -> Access -> Applications; the AUD tag is on the application's
# overview page). They live in the shared secrets file every app reads
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
