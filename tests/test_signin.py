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
