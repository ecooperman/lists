"""How this app is wired to shared_python's own sign-in (/auth/login, /auth/callback,
/auth/logout). The flow itself is tested where the code lives, in shared-python; here:
the routes are mounted, signed-out visitors to a page are sent to sign in, Cloudflare
visitors are left alone, and the Log out link knows which sign-in a person used."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from shared_python import auth as shared_auth
from shared_python import settings

ISSUER = "https://login.example.com"
CLIENT = "client-123"


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def own_sign_in(monkeypatch, key):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", CLIENT)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", CLIENT)
    monkeypatch.setattr(shared_auth, "_oidc_signing_key", lambda _token: key.public_key())


def id_token(key, email="alice@example.com"):
    return jwt.encode({"iss": ISSUER, "aud": CLIENT, "exp": int(time.time()) + 300, "email": email}, key, algorithm="RS256")


def test_the_sign_in_routes_do_not_exist_until_configured(client):
    for path in ("/auth/login", "/auth/callback", "/auth/logout"):
        assert client.get(path, follow_redirects=False).status_code == 404


@pytest.mark.parametrize("page", ["/", "/list.html?id=2", "/categories.html"])
def test_a_signed_out_visitor_is_sent_to_sign_in_and_then_back(client, own_sign_in, page):
    resp = client.get(page, follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["location"].startswith("/auth/login?next=")


def test_a_signed_in_person_gets_the_page(client, own_sign_in, key, alice):
    client.cookies.set("oidc_session", id_token(key, alice.email))
    assert client.get("/", follow_redirects=False).status_code == 200


def test_a_person_with_no_account_still_gets_the_explanation_not_a_redirect_loop(client, own_sign_in, key):
    client.cookies.set("oidc_session", id_token(key, "stranger@example.com"))
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 403 and "access" in resp.text.lower()


def test_the_api_stays_a_401_not_a_redirect(client, own_sign_in):
    assert client.get("/api/me", follow_redirects=False).status_code == 401


def test_the_log_out_link_goes_to_the_apps_own_sign_in_when_that_was_used(client, own_sign_in, key, alice):
    client.cookies.set("oidc_session", id_token(key, alice.email))
    assert client.get("/api/me").json()["logout_url"] == "/auth/logout"


def test_the_log_out_link_stays_cloudflares_for_cloudflare_visitors(client, own_sign_in, key, alice, monkeypatch):
    monkeypatch.setattr(settings, "CF_TEAM_DOMAIN", "team.cloudflareaccess.com")
    monkeypatch.setattr(settings, "CF_ACCESS_AUD", "cf-aud")
    monkeypatch.setattr(shared_auth, "_signing_key", lambda _token: key.public_key())
    cf = jwt.encode({"email": alice.email, "aud": ["cf-aud"], "exp": int(time.time()) + 300}, key, algorithm="RS256")
    resp = client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": cf})
    assert resp.status_code == 200 and resp.json()["logout_url"] is None
    assert client.get("/", headers={"Cf-Access-Jwt-Assertion": cf}, follow_redirects=False).status_code == 200  # no redirect for them


def test_with_no_own_sign_in_configured_the_link_is_the_default(client, alice):
    assert client.get("/api/me", headers=alice.headers).json()["logout_url"] is None


# --- through the shared front door (the dashboard): this app only checks the cookie ---------------------

FRONT = "https://dashboard.example.org"


@pytest.fixture()
def verify_only(monkeypatch, key):
    """No client id or secret here: only the issuer, the audience and where the front door is."""
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", CLIENT)
    monkeypatch.setattr(settings, "OIDC_LOGIN_URL", FRONT + "/auth/login")
    monkeypatch.setattr(shared_auth, "_oidc_signing_key", lambda _token: key.public_key())


def test_a_signed_out_visitor_goes_to_the_front_door_and_comes_back_to_this_page(client, verify_only):
    resp = client.get("/list.html?id=2", headers={"host": "lists.example.org"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith(FRONT + "/auth/login?next=")
    assert "https%3A%2F%2Flists.example.org%2Flist.html%3Fid%3D2" in resp.headers["location"]


def test_the_api_stays_a_401_for_a_signed_out_visitor(client, verify_only):
    assert client.get("/api/me", follow_redirects=False).status_code == 401


def test_the_shared_cookie_signs_a_person_in_here(client, verify_only, key, alice):
    client.cookies.set("oidc_session", id_token(key, alice.email))
    assert client.get("/", follow_redirects=False).status_code == 200
    me = client.get("/api/me").json()
    assert me["email"] == alice.email and me["logout_url"] == FRONT + "/auth/logout"


def test_there_are_no_sign_in_routes_here_only_at_the_front_door(client, verify_only):
    for path in ("/auth/login", "/auth/callback", "/auth/logout"):
        assert client.get(path, follow_redirects=False).status_code == 404


def test_the_no_access_page_logs_out_through_the_front_door(client, verify_only, key):
    client.cookies.set("oidc_session", id_token(key, "stranger@example.com"))
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 403 and f'href="{FRONT}/auth/logout"' in resp.text


def test_someone_with_no_account_is_pointed_at_the_dashboard_to_ask_for_one(client, verify_only, key):
    client.cookies.set("oidc_session", id_token(key, "stranger@example.com"))
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 403 and f'href="{FRONT}/"' in resp.text and "Ask for access" in resp.text


def test_someone_whose_access_was_removed_is_not_sent_to_ask_again(client, admin, alice, request, key):
    rows = admin.get("/api/admin/users").json()
    admin.post(f"/api/admin/users/{next(r['id'] for r in rows if r['email'] == alice.email)}/revoke")
    request.getfixturevalue("verify_only")  # production sign-in from here on (the admin headers above are Cloudflare's)
    client.cookies.set("oidc_session", id_token(key, alice.email))
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 403 and "Your access was removed" in resp.text and "Ask for access" not in resp.text


def test_the_no_access_page_still_logs_out_through_cloudflare_by_default(client, sign_in):
    sign_in("stranger@example.com", enabled=False)
    resp = client.get("/", headers={"Cf-Access-Authenticated-User-Email": "stranger@example.com"}, follow_redirects=False)
    assert resp.status_code == 403 and 'href="/cdn-cgi/access/logout"' in resp.text
    assert "Ask for access" not in resp.text  # no dashboard in front of this app: nowhere to send them


def test_no_route_answers_with_data_when_nobody_is_signed_in(client, verify_only):
    """The guard for taking the Cloudflare login off this hostname: with no sign-in at all, every route in the
    app is refused (the API) or sends the visitor to sign in (the pages). A route added later without its sign-in
    check fails here before it can go live."""
    import re

    from app.main import app

    pages = ["/", "/list.html", "/categories.html", "/invites.html", "/users.html", "/contacts.html", "/link-labels.html"]
    answered = []
    for shown, operations in app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", "1", shown)
        if path in pages:
            continue  # the pages are checked below
        for method in operations:
            if method.upper() in ("HEAD", "OPTIONS"):
                continue
            body = {"json": {}} if method.upper() in ("POST", "PUT", "PATCH") else {}
            resp = client.request(method.upper(), path, follow_redirects=False, **body)
            if resp.status_code not in (401, 403, 404, 405, 503) and not (resp.status_code == 200 and path == "/api/version"):
                answered.append((method.upper(), shown, resp.status_code))
    for page in pages:
        resp = client.get(page, follow_redirects=False)
        if resp.status_code != 302:
            answered.append(("GET", page, resp.status_code))
    assert not answered, f"answered without a sign-in: {answered}"


def test_approving_an_invite_never_touches_cloudflare_when_signing_in_through_the_front_door(alice, admin, monkeypatch):
    """Cloudflare is configured here (and any call to it fails the test, see conftest), yet approval goes through:
    with the shared front door in use there is no Cloudflare gate to let anyone through, and no seat cap."""
    monkeypatch.setattr(settings, "CF_API_TOKEN", "token")
    monkeypatch.setattr(settings, "CF_ACCOUNT_ID", "acct")
    monkeypatch.setattr(settings, "CF_INVITEES_GROUP_ID", "group")
    monkeypatch.setattr(settings, "ACCESS_SEAT_CAP", 0)  # through Cloudflare even the first approval would be refused
    monkeypatch.setattr(settings, "OIDC_ISSUER", "https://login.example.com")
    monkeypatch.setattr(settings, "OIDC_LOGIN_URL", "https://dashboard.example.org/auth/login")
    invite = alice.post("/api/app-invites", {"email": "newbie@example.com"}).json()
    resp = admin.post(f"/api/admin/invites/{invite['id']}/approve")
    assert resp.status_code == 200 and resp.json()["status"] == "approved"


# --- cross-app request forgery -------------------------------------------------------------------------------------------


def test_every_route_that_changes_something_refuses_a_request_from_another_app_or_site(client):
    """The sign-in cookie covers every subdomain and subdomains are the same site, so a page on another app could make a
    visitor's browser change things here. The browser marks such a request (Sec-Fetch-Site), and every route that
    changes anything must refuse it, whatever the cookie says (shared_python.csrf)."""
    import re

    from app.main import app

    tried = 0
    for shown, operations in app.openapi()["paths"].items():
        path = re.sub(r"\{[^}]+\}", "1", shown)
        for method in operations:
            if method.upper() not in ("POST", "PUT", "PATCH", "DELETE"):
                continue
            for site in ("same-site", "cross-site"):
                resp = client.request(method.upper(), path, json={}, headers={"Sec-Fetch-Site": site, "Origin": "https://lists.example.org"})
                assert resp.status_code == 403 and "didn't come from this app" in resp.text, (method, shown, site, resp.status_code)
                tried += 1
    assert tried > 4  # guards against the loop silently covering nothing


def test_a_change_from_the_apps_own_page_still_goes_through_the_guard(client):
    from app.main import app

    for shown, operations in app.openapi()["paths"].items():
        if "post" in operations and "{" not in shown:
            resp = client.post(shown, json={}, headers={"Sec-Fetch-Site": "same-origin"})
            assert "didn't come from this app" not in resp.text  # 422, 404, 200... but never the guard's refusal
            return
    pytest.fail("no plain POST route found")
