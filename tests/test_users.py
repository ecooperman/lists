"""Who may use the app: an account here is something the administrator grants
(approving an invite or adding someone), not something anyone who passes
Cloudflare's shared login gate gets by turning up. These cover the Users page's
add / remove / restore / delete and what each leaves behind."""
import pytest
from sqlalchemy import text

from shared_python import cloudflare, notify

from app import models
from app.database import engine
from tests.test_access import make_item, make_list, share

URL = "/api/admin/users"


@pytest.fixture()
def allowed(monkeypatch):
    """Stand-in for Cloudflare: the emails that were let through the gate."""
    emails = []
    monkeypatch.setattr(cloudflare, "allow_email", emails.append)
    return emails


@pytest.fixture()
def emails(monkeypatch):
    mails = []
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body: mails.append((to, subject, body)) or True)
    return mails


def make_category(person, name):
    resp = person.post("/api/categories", {"name": name, "color": "#aabbcc"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_contact(person, first_name):
    resp = person.post("/api/contacts", {"first_name": first_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def user_row(admin, email):
    return next((u for u in admin.get(URL).json() if u["email"] == email), None)


def user_id(admin, email):
    return user_row(admin, email)["id"]


# --- the page's list ---------------------------------------------------------


def test_only_the_administrator_may_use_the_users_endpoints(alice, bob):
    for call in (
        lambda: alice.get(URL),
        lambda: alice.post(URL, {"email": "x@example.com"}),
        lambda: alice.post(f"{URL}/1/revoke"),
        lambda: alice.post(f"{URL}/1/restore"),
        lambda: alice.delete(f"{URL}/1"),
    ):
        assert call().status_code == 403


def test_the_list_shows_everyone_with_what_they_own(admin, alice, bob):
    lst = make_list(alice, "Gifts")
    make_item(alice, lst["id"])
    make_item(alice, lst["id"], "Hat")
    share(alice, lst["id"], bob, "edit")
    make_contact(alice, "Mum")
    make_category(alice, "Holidays")
    make_list(bob, "Bobs")

    rows = {u["email"]: u for u in admin.get(URL).json()}
    assert set(rows) == {admin.email, alice.email, bob.email}
    a, b = rows[alice.email], rows[bob.email]
    assert (a["owned_lists"], a["items"], a["contacts"], a["categories"], a["people_on_their_lists"]) == (1, 2, 1, 1, 1)
    assert (b["owned_lists"], b["shared_with_them"]) == (1, 1)
    assert a["status"] == "active" and a["is_admin"] is False
    assert "legacy-owner@lists.invalid" not in rows


# --- no account until one is granted ---------------------------------------------


def test_a_removed_person_cant_use_anything_but_keeps_their_data(admin, alice, bob):
    lst = make_list(alice, "Gifts")
    make_item(alice, lst["id"])
    share(alice, lst["id"], bob, "edit")

    row = admin.post(f"{URL}/{user_id(admin, bob.email)}/revoke").json()
    assert row["status"] == "removed"
    for url in ("/api/me", "/api/lists", f"/api/lists/{lst['id']}/items", "/api/contacts"):
        resp = bob.get(url)
        assert resp.status_code == 403 and "removed" in resp.json()["detail"]
    assert bob.post("/api/lists", {"name": "Sneaky"}).status_code == 403
    # Nothing was erased: the list is still shared with them in the database.
    assert alice.get(f"/api/lists/{lst['id']}/members").json()[1]["email"] == bob.email

    admin.post(f"{URL}/{row['id']}/restore")
    assert [l["name"] for l in bob.get("/api/lists").json()] == ["Gifts"]


def test_revoking_here_doesnt_touch_cloudflare(admin, alice, allowed, monkeypatch):
    calls = []
    monkeypatch.setattr(cloudflare, "allow_email", lambda e: calls.append(e))
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    assert calls == []  # another app may still need the person at the gate


def test_the_administrator_cant_be_removed_or_deleted(admin, db):
    admin.get("/api/me")
    me = user_id(admin, admin.email)
    assert admin.post(f"{URL}/{me}/revoke").status_code == 400
    assert admin.delete(f"{URL}/{me}").status_code == 400


def test_the_placeholder_owner_and_unknown_ids_are_not_people(admin):
    for call in (
        lambda i: admin.post(f"{URL}/{i}/revoke"),
        lambda i: admin.post(f"{URL}/{i}/restore"),
        lambda i: admin.delete(f"{URL}/{i}"),
    ):
        assert call(999).status_code == 404
    # (The administrator's first request above took over the migration's placeholder.)
    with engine.begin() as conn:
        conn.execute(text("insert into users (email) values ('legacy-owner@lists.invalid')"))
        placeholder = conn.execute(text("select id from users where email = 'legacy-owner@lists.invalid'")).scalar()
    assert admin.post(f"{URL}/{placeholder}/revoke").status_code == 404


def test_you_cant_share_with_or_invite_someone_who_was_removed(admin, alice, bob):
    lst = make_list(alice)
    admin.post(f"{URL}/{user_id(admin, bob.email)}/revoke")
    add = alice.post(f"/api/lists/{lst['id']}/members", {"email": bob.email, "role": "view"})
    ask = alice.post(f"/api/lists/{lst['id']}/invites", {"email": bob.email, "role": "view"})
    app_ask = alice.post("/api/app-invites", {"email": bob.email})
    for resp in (add, ask, app_ask):
        assert resp.status_code == 409 and "removed" in resp.json()["detail"] and bob.email in resp.json()["detail"]


def test_an_approved_invite_for_a_removed_person_switches_them_back_on(admin, alice, bob, allowed, monkeypatch):
    # An invite that was waiting when they were removed: approving it is the administrator's decision.
    from app import crud
    from app.database import SessionLocal

    with SessionLocal() as s:
        invite, _ = crud.create_invite(s, None, crud.get_account(s, alice.email), "newbie@example.com", "view", for_app=True)
        invite_id = invite.id
        crud.enable_user(s, "newbie@example.com")
        crud.set_user_status(s, crud.get_account(s, "newbie@example.com"), models.USER_REMOVED)
    assert admin.post(f"/api/admin/invites/{invite_id}/approve").status_code == 200
    assert user_row(admin, "newbie@example.com")["status"] == "active"


# --- adding and restoring --------------------------------------------------------------


def test_adding_someone_lets_them_through_the_gate_gives_an_account_and_emails_them(admin, sign_in, allowed, emails):
    dana = sign_in("dana@example.com", enabled=False)
    assert dana.get("/api/lists").status_code == 403

    resp = admin.post(URL, {"email": "  Dana@Example.com "})
    assert resp.status_code == 200 and resp.json()["email"] == "dana@example.com" and resp.json()["status"] == "active"
    assert allowed == ["dana@example.com"]
    assert dana.get("/api/lists").json() == []
    assert [to for to, _, _ in emails] == ["dana@example.com"]
    assert "one-time PIN" in emails[0][2]


def test_adding_someone_who_already_has_access_is_refused(admin, alice, allowed):
    resp = admin.post(URL, {"email": alice.email})
    assert resp.status_code == 409 and alice.email in resp.json()["detail"]
    assert allowed == []


def test_adding_a_removed_person_restores_them_with_their_data(admin, alice, allowed):
    make_list(alice, "Gifts")
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    assert admin.post(URL, {"email": alice.email}).json()["status"] == "active"
    assert [l["name"] for l in alice.get("/api/lists").json()] == ["Gifts"]


def test_adding_rejects_things_that_are_not_emails(admin, allowed):
    assert admin.post(URL, {"email": "nope"}).status_code in (400, 422)
    assert allowed == []


@pytest.mark.parametrize(
    "error, status",
    [
        (cloudflare.NotConfigured("off"), 503),
        (cloudflare.SeatCapReached("full"), 409),
        (cloudflare.CloudflareError("down"), 502),
    ],
)
def test_if_cloudflare_cant_do_it_nobody_is_added_or_restored(admin, alice, sign_in, monkeypatch, error, status):
    def fail(email):
        raise error

    monkeypatch.setattr(cloudflare, "allow_email", fail)
    assert admin.post(URL, {"email": "dana@example.com"}).status_code == status
    assert user_row(admin, "dana@example.com") is None

    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    assert admin.post(f"{URL}/{user_id(admin, alice.email)}/restore").status_code == status
    assert user_row(admin, alice.email)["status"] == "removed"


# --- deleting ---------------------------------------------------------------------------


def test_deleting_needs_the_person_removed_first(admin, alice):
    make_list(alice)
    resp = admin.delete(f"{URL}/{user_id(admin, alice.email)}")
    assert resp.status_code == 409
    assert user_row(admin, alice.email)["owned_lists"] == 1


def test_deleting_erases_what_they_own_and_keeps_a_removed_account(admin, alice, bob, carol, allowed, db):
    mine = make_list(alice, "Alice's")
    make_item(alice, mine["id"])
    share(alice, mine["id"], bob, "view")
    shared_to_alice = make_list(bob, "Bob's")
    share(bob, shared_to_alice["id"], alice, "edit")
    mum = make_contact(alice, "Mum")
    make_item(alice, mine["id"], "For mum", recipient_id=mum["id"])
    make_category(alice, "Holidays")
    # A request alice made, and one made on her list by someone else.
    assert alice.post("/api/app-invites", {"email": "newbie@example.com"}).status_code == 200
    assert alice.post(f"/api/lists/{mine['id']}/invites", {"email": "other@example.com", "role": "view"}).status_code == 200

    alice_id = user_id(admin, alice.email)
    admin.post(f"{URL}/{alice_id}/revoke")
    assert admin.delete(f"{URL}/{alice_id}").json() == {"ok": True}

    row = user_row(admin, alice.email)
    assert row["status"] == "removed" and (row["owned_lists"], row["items"], row["contacts"], row["categories"]) == (0, 0, 0, 0)
    assert row["shared_with_them"] == 0
    # Her list is gone for bob too; bob's own list is intact and she is no longer on it.
    assert [l["name"] for l in bob.get("/api/lists").json()] == ["Bob's"]
    assert [m["email"] for m in bob.get(f"/api/lists/{shared_to_alice['id']}/members").json()] == [bob.email]
    assert db.query(models.Invite).count() == 0
    assert db.query(models.Item).count() == 0 and db.query(models.Contact).count() == 0
    # She still can't walk back in with a fresh account.
    assert alice.get("/api/lists").status_code == 403
    assert db.query(models.User).filter_by(email=alice.email).count() == 1

    # Restoring gives her a clean, empty account.
    admin.post(f"{URL}/{alice_id}/restore")
    assert alice.get("/api/lists").json() == []


def test_deleting_one_person_leaves_everyone_elses_data_alone(admin, alice, bob):
    theirs = make_list(bob, "Bobs")
    make_item(bob, theirs["id"])
    make_contact(bob, "Sis")
    make_category(bob, "Work")
    make_list(alice)
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    admin.delete(f"{URL}/{user_id(admin, alice.email)}")
    row = user_row(admin, bob.email)
    assert (row["owned_lists"], row["items"], row["contacts"], row["categories"]) == (1, 1, 1, 1)


def test_deleting_removes_a_locked_list_too(admin, alice):
    lst = make_list(alice, "Locked")
    assert alice.patch(f"/api/lists/{lst['id']}", {"locked": True}).status_code == 200
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    assert admin.delete(f"{URL}/{user_id(admin, alice.email)}").status_code == 200
    assert user_row(admin, alice.email)["owned_lists"] == 0


def test_people_the_deleted_person_let_in_keep_their_accounts(admin, alice, allowed, sign_in, db):
    alice.post("/api/app-invites", {"email": "dana@example.com"})
    invite = admin.get("/api/admin/invites").json()[0]
    admin.post(f"/api/admin/invites/{invite['id']}/approve")
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    admin.delete(f"{URL}/{user_id(admin, alice.email)}")
    assert user_row(admin, "dana@example.com")["status"] == "active"


# --- the schema -----------------------------------------------------------------------


def test_accounts_that_existed_before_the_column_are_active():
    """The migration's default is what makes today's accounts keep working."""
    with engine.begin() as conn:
        conn.execute(text("insert into users (email) values ('old@example.com')"))
        status = conn.execute(text("select status from users where email = 'old@example.com'")).scalar()
    assert status == "active"


# --- the pages ---------------------------------------------------------------------


PAGES = ("/", "/list.html", "/categories.html", "/invites.html", "/contacts.html")


def test_pages_open_for_people_with_access(alice, admin):
    for page in PAGES:
        assert alice.get(page).status_code == 200
        assert admin.get(page).status_code == 200


def test_pages_explain_instead_of_showing_an_empty_app_to_people_without_access(sign_in, admin, alice):
    stranger = sign_in("stranger@example.com", enabled=False)
    for page in PAGES + ("/users.html",):
        resp = stranger.get(page)
        assert resp.status_code == 403
        assert "have access yet" in resp.text and "stranger@example.com" in resp.text
        assert "Log out" in resp.text and "app-nav-mount" not in resp.text  # none of the app itself

    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    removed = alice.get("/")
    assert removed.status_code == 403 and "Your access was removed" in removed.text


def test_the_users_page_is_for_the_administrator_only(admin, alice):
    assert admin.get("/users.html").status_code == 200
    resp = alice.get("/users.html")
    assert resp.status_code == 403 and "Administrators only" in resp.text


# --- who counts as able to sign in ---------------------------------------------------------------


def test_a_second_administrator_gets_an_account_on_first_sight(admin, sign_in, monkeypatch, db):
    from app import config

    other = sign_in("boss2@example.com", enabled=False)
    monkeypatch.setattr(config, "ADMIN_EMAILS", config.ADMIN_EMAILS | {"boss2@example.com"})
    admin.get("/api/me")  # the first administrator takes over the pre-accounts placeholder
    assert other.get("/api/me").json()["is_admin"] is True
    assert db.query(models.User).filter_by(email="boss2@example.com").count() == 1


def test_can_sign_in_needs_an_active_account(db):
    from app import crud
    from app.signin import can_sign_in

    assert can_sign_in(db, "nobody@example.com") is False  # no account
    user = crud.enable_user(db, "dana@example.com")
    assert can_sign_in(db, "dana@example.com") is True
    crud.set_user_status(db, user, models.USER_REMOVED)
    assert can_sign_in(db, "dana@example.com") is False
