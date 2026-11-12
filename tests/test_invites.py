"""Letting new people in: a list's owner asks, the administrator decides. The
Cloudflare call and the notification are stubbed here (shared-python's own tests
cover those); what matters in this file is who may ask
and decide, how many times, and what each outcome leaves behind."""
import pytest

from shared_python import cloudflare, notify

from app import config, models
from tests.test_access import make_list, share

NEWBIE = "newbie@example.com"


@pytest.fixture()
def allowed(monkeypatch):
    """Stand-in for Cloudflare: the emails that were let through the gate."""
    emails = []
    monkeypatch.setattr(cloudflare, "allow_email", emails.append)
    return emails


@pytest.fixture()
def sent(monkeypatch):
    """Stand-in for the notification channels: what the administrator was told."""
    messages = []
    monkeypatch.setattr(notify, "notify", lambda title, message, link=None: messages.append((title, message, link)))
    return messages


def ask(person, list_id, email=NEWBIE, role="edit"):
    return person.post(f"/api/lists/{list_id}/invites", {"email": email, "role": role})


# --- adding people vs. asking for them ---------------------------------------


def test_asking_for_a_new_person_waits_for_approval(alice, admin, allowed, sent):
    lst = make_list(alice)
    resp = ask(alice, lst["id"], "  NewBie@Example.com ")
    assert resp.status_code == 200
    assert (resp.json()["email"], resp.json()["status"], resp.json()["role"]) == (NEWBIE, "pending", "edit")

    assert allowed == []  # nobody let through yet
    members = [m["email"] for m in alice.get(f"/api/lists/{lst['id']}/members").json()]
    assert members == [alice.email]
    assert [i["email"] for i in alice.get(f"/api/lists/{lst['id']}/invites").json()] == [NEWBIE]


def test_the_administrator_is_told_about_each_request(alice, allowed, sent):
    lst = make_list(alice)
    ask(alice, lst["id"])
    assert len(sent) == 1
    title, message, link = sent[0]
    assert title == "Lists: invite waiting for approval"
    assert alice.email in message and NEWBIE in message and "edit" in message
    assert link == f"{config.PUBLIC_URL}/invites.html"


def test_a_failing_notification_doesnt_fail_the_request(alice, monkeypatch):
    def broken(title, message, link):
        raise RuntimeError("push service is down")

    monkeypatch.setattr(notify, "CHANNELS", {"ntfy": broken})
    lst = make_list(alice)
    assert ask(alice, lst["id"]).status_code == 200


def test_someone_with_an_account_is_added_not_invited(alice, bob):
    lst = make_list(alice)
    bob.get("/api/me")
    assert ask(alice, lst["id"], bob.email).status_code == 409


def test_a_bad_address_or_a_repeat_request_is_refused(alice):
    lst = make_list(alice)
    assert ask(alice, lst["id"], "not-an-email").status_code == 400
    assert ask(alice, lst["id"]).status_code == 200
    assert ask(alice, lst["id"], NEWBIE.upper()).status_code == 409


def test_only_the_owner_can_ask(alice, bob, carol):
    lst = make_list(alice)
    share(alice, lst["id"], bob, "edit")
    assert ask(bob, lst["id"]).status_code == 403  # an editor can't manage who has access
    assert ask(carol, lst["id"]).status_code == 404  # a stranger can't even see the list
    assert bob.get(f"/api/lists/{lst['id']}/invites").status_code == 403
    assert carol.get(f"/api/lists/{lst['id']}/invites").status_code == 404


# --- who counts as someone who can sign in --------------------------------------


@pytest.fixture()
def let_in(monkeypatch):
    """Cloudflare is configured: the returned set is who's in its allowed group."""
    group = set()
    monkeypatch.setattr(cloudflare, "is_let_in", lambda email, admin_emails=(): email in group)
    return group


def members_of(person, list_id):
    return [m["email"] for m in person.get(f"/api/lists/{list_id}/members").json()]


def test_an_account_that_cloudflare_wont_let_in_cant_simply_be_added(alice, bob, let_in):
    lst = make_list(alice)
    bob.get("/api/me")  # bob has an account...
    resp = alice.post(f"/api/lists/{lst['id']}/members", {"email": bob.email, "role": "view"})
    assert resp.status_code == 404  # ...but isn't in the allowed group, so he couldn't open the list
    assert members_of(alice, lst["id"]) == [alice.email]

    let_in.add(bob.email)
    assert alice.post(f"/api/lists/{lst['id']}/members", {"email": bob.email, "role": "view"}).status_code == 200


def test_someone_through_the_gate_for_another_app_still_has_to_be_invited_here(alice, sign_in, let_in, db, admin, allowed, sent):
    let_in.add("dana@example.com")  # e.g. invited to Trips: Cloudflare's group is shared by the apps
    lst = make_list(alice)
    body = {"email": "Dana@Example.com", "role": "edit"}
    assert alice.post(f"/api/lists/{lst['id']}/members", body).status_code == 404  # no account here, so no sharing
    assert db.query(models.User).filter_by(email="dana@example.com").count() == 0
    dana = sign_in("dana@example.com", enabled=False)
    assert dana.get("/api/lists").status_code == 403  # nor can she use the app

    # Asking works, and approving gives her an account and the list.
    invite = ask(alice, lst["id"], "Dana@Example.com")
    assert invite.status_code == 200
    assert admin.post(f"/api/admin/invites/{invite.json()['id']}/approve").status_code == 200
    assert [(l["name"], l["my_role"]) for l in dana.get("/api/lists").json()] == [("Gifts", "edit")]


def test_someone_who_can_already_sign_in_is_added_not_invited(alice, let_in, sign_in):
    sign_in("dana@example.com")  # enabled here
    let_in.add("dana@example.com")
    lst = make_list(alice)
    assert ask(alice, lst["id"], "dana@example.com").status_code == 409


def test_an_account_that_cant_sign_in_can_be_invited_back(alice, bob, admin, let_in, allowed, sent, db):
    bob.get("/api/me")  # an account, but removed from the group (or never put in it)
    lst = make_list(alice)
    resp = ask(alice, lst["id"], bob.email)
    assert (resp.status_code, resp.json()["status"]) == (200, "pending")

    assert admin.post(f"/api/admin/invites/{resp.json()['id']}/approve").status_code == 200
    assert allowed == [bob.email]  # approving is what puts him back in the group
    assert members_of(alice, lst["id"]) == [alice.email, bob.email]
    assert db.query(models.User).filter_by(email=bob.email).count() == 1


def test_the_administrator_can_bring_back_someone_removed_from_the_group(admin, bob, let_in, allowed, sent):
    bob.get("/api/me")
    lst = make_list(admin)
    assert admin.post(f"/api/lists/{lst['id']}/members", {"email": bob.email, "role": "view"}).status_code == 404
    resp = ask(admin, lst["id"], bob.email, "view")
    assert (resp.status_code, resp.json()["status"]) == (200, "approved")  # their own request, approved at once
    assert allowed == [bob.email]
    assert bob.email in members_of(admin, lst["id"])


def test_if_cloudflare_cant_be_asked_nobody_is_added_or_invited(alice, bob, monkeypatch):
    def down(email, admin_emails=()):
        raise cloudflare.CloudflareError("Couldn't reach Cloudflare - try again in a moment")

    monkeypatch.setattr(cloudflare, "is_let_in", down)
    bob.get("/api/me")
    lst = make_list(alice)
    for resp in (
        alice.post(f"/api/lists/{lst['id']}/members", {"email": bob.email, "role": "view"}),
        ask(alice, lst["id"], bob.email),
    ):
        assert resp.status_code == 502 and "Cloudflare" in resp.json()["detail"]
    assert members_of(alice, lst["id"]) == [alice.email]
    assert alice.get(f"/api/lists/{lst['id']}/invites").json() == []


# --- how many each person may ask for ---------------------------------------------


def test_each_person_gets_a_limited_number_of_invites(alice, monkeypatch, allowed, sent):
    monkeypatch.setattr(config, "INVITES_PER_USER", 2)
    lst = make_list(alice)
    assert alice.get("/api/me").json()["invites_left"] == 2
    assert ask(alice, lst["id"], "a@example.com").status_code == 200
    assert ask(alice, lst["id"], "b@example.com").status_code == 200
    assert alice.get("/api/me").json()["invites_left"] == 0
    assert ask(alice, lst["id"], "c@example.com").status_code == 403


def test_asking_for_the_same_person_on_another_list_costs_nothing_more(alice, monkeypatch, allowed, sent):
    monkeypatch.setattr(config, "INVITES_PER_USER", 1)
    first, second = make_list(alice, "First"), make_list(alice, "Second")
    assert ask(alice, first["id"], "a@example.com").status_code == 200
    assert ask(alice, second["id"], "a@example.com").status_code == 200
    assert ask(alice, second["id"], "b@example.com").status_code == 403


def test_withdrawing_a_waiting_request_gives_the_invite_back(alice, monkeypatch, allowed, sent):
    monkeypatch.setattr(config, "INVITES_PER_USER", 1)
    lst = make_list(alice)
    invite = ask(alice, lst["id"], "a@example.com").json()
    assert ask(alice, lst["id"], "b@example.com").status_code == 403
    assert alice.delete(f"/api/lists/{lst['id']}/invites/{invite['id']}").status_code == 200
    assert alice.get("/api/me").json()["invites_left"] == 1
    assert ask(alice, lst["id"], "b@example.com").status_code == 200


def test_a_declined_request_still_uses_up_the_invite(alice, admin, monkeypatch, allowed, sent):
    monkeypatch.setattr(config, "INVITES_PER_USER", 1)
    lst = make_list(alice)
    invite = ask(alice, lst["id"], "a@example.com").json()
    assert admin.post(f"/api/admin/invites/{invite['id']}/decline").status_code == 200
    assert ask(alice, lst["id"], "b@example.com").status_code == 403
    # ...and she can neither withdraw it nor ask again for the same person.
    assert alice.delete(f"/api/lists/{lst['id']}/invites/{invite['id']}").status_code == 409
    assert ask(alice, lst["id"], "a@example.com").status_code == 409
    shown = alice.get(f"/api/lists/{lst['id']}/invites").json()
    assert [(i["email"], i["status"]) for i in shown] == [("a@example.com", "declined")]


def test_the_administrator_has_no_limit_and_needs_no_approval(admin, monkeypatch, allowed, sent):
    monkeypatch.setattr(config, "INVITES_PER_USER", 1)
    lst = make_list(admin)
    assert admin.get("/api/me").json()["invites_left"] is None
    for email in ("a@example.com", "b@example.com", "c@example.com"):
        resp = ask(admin, lst["id"], email)
        assert (resp.status_code, resp.json()["status"]) == (200, "approved")
    assert allowed == ["a@example.com", "b@example.com", "c@example.com"]
    assert sent == []  # nobody needs telling about their own decision
    members = [m["email"] for m in admin.get(f"/api/lists/{lst['id']}/members").json()]
    assert members == [admin.email, "a@example.com", "b@example.com", "c@example.com"]


# --- the administrator decides ----------------------------------------------------


def test_the_queue_shows_who_asked_for_whom(alice, admin, allowed, sent):
    lst = make_list(alice, "Birthday ideas")
    ask(alice, lst["id"], role="view")
    queue = admin.get("/api/admin/invites").json()
    assert len(queue) == 1
    assert (queue[0]["email"], queue[0]["invited_by_email"], queue[0]["list_name"], queue[0]["role"]) == (
        NEWBIE,
        alice.email,
        "Birthday ideas",
        "view",
    )
    assert admin.get("/api/me").json()["pending_invites"] == 1
    assert alice.get("/api/me").json()["pending_invites"] == 0  # the count is the administrator's


def test_approving_lets_them_through_and_puts_them_on_the_list(alice, admin, sign_in, allowed, sent):
    lst = make_list(alice)
    invite = ask(alice, lst["id"], role="edit").json()

    resp = admin.post(f"/api/admin/invites/{invite['id']}/approve")
    assert resp.status_code == 200 and resp.json()["status"] == "approved"
    assert allowed == [NEWBIE]

    # They sign in for the first time and the list is already there.
    newbie = sign_in(NEWBIE)
    assert [(l["name"], l["my_role"]) for l in newbie.get("/api/lists").json()] == [("Gifts", "edit")]
    # ...and is now a member, so the request is no longer listed as outstanding.
    assert NEWBIE in [m["email"] for m in alice.get(f"/api/lists/{lst['id']}/members").json()]
    assert alice.get(f"/api/lists/{lst['id']}/invites").json() == []
    assert admin.get("/api/admin/invites").json() == []
    assert admin.get("/api/me").json()["pending_invites"] == 0


def test_declining_changes_nothing_in_cloudflare_or_the_list(alice, admin, sign_in, allowed, sent):
    lst = make_list(alice)
    invite = ask(alice, lst["id"]).json()
    assert admin.post(f"/api/admin/invites/{invite['id']}/decline").status_code == 200
    assert allowed == []
    assert NEWBIE not in [m["email"] for m in alice.get(f"/api/lists/{lst['id']}/members").json()]
    assert sign_in(NEWBIE).get("/api/lists").json() == []


def test_a_request_can_only_be_decided_once(alice, admin, allowed, sent):
    lst = make_list(alice)
    invite = ask(alice, lst["id"]).json()
    assert admin.post(f"/api/admin/invites/{invite['id']}/approve").status_code == 200
    assert admin.post(f"/api/admin/invites/{invite['id']}/approve").status_code == 409
    assert admin.post(f"/api/admin/invites/{invite['id']}/decline").status_code == 409
    assert admin.post("/api/admin/invites/9999/approve").status_code == 404
    assert allowed == [NEWBIE]


def test_only_the_administrator_can_see_or_decide(alice, bob, admin, allowed, sent):
    lst = make_list(alice)
    invite = ask(alice, lst["id"]).json()
    for who in (alice, bob):  # even the person who asked
        assert who.get("/api/admin/invites").status_code == 403
        assert who.post(f"/api/admin/invites/{invite['id']}/approve").status_code == 403
        assert who.post(f"/api/admin/invites/{invite['id']}/decline").status_code == 403
    assert allowed == []
    assert [i["email"] for i in admin.get("/api/admin/invites").json()] == [NEWBIE]


@pytest.mark.parametrize(
    "error, status",
    [
        (cloudflare.NotConfigured("not set up"), 503),
        (cloudflare.SeatCapReached("group is full"), 409),
        (cloudflare.CloudflareError("Cloudflare refused"), 502),
    ],
    ids=["not configured", "seat cap", "cloudflare error"],
)
def test_if_cloudflare_cant_do_it_the_request_stays_waiting(alice, admin, sent, monkeypatch, error, status):
    def refuse(email):
        raise error

    monkeypatch.setattr(cloudflare, "allow_email", refuse)
    lst = make_list(alice)
    invite = ask(alice, lst["id"]).json()

    resp = admin.post(f"/api/admin/invites/{invite['id']}/approve")
    assert resp.status_code == status and resp.json()["detail"] == str(error)
    # Nobody is recorded as let in who still can't sign in.
    assert NEWBIE not in [m["email"] for m in alice.get(f"/api/lists/{lst['id']}/members").json()]
    assert [i["email"] for i in admin.get("/api/admin/invites").json()] == [NEWBIE]


def test_locally_with_cloudflare_unset_approving_still_works(alice, admin, sent):
    lst = make_list(alice)
    invite = ask(alice, lst["id"]).json()
    assert admin.post(f"/api/admin/invites/{invite['id']}/approve").status_code == 200


# --- withdrawing, and what a deleted list leaves behind ----------------------------


def test_only_a_lists_owner_can_withdraw_its_requests(alice, bob, sent):
    mine, other = make_list(alice, "Mine"), make_list(bob, "Other")
    invite = ask(alice, mine["id"]).json()
    assert bob.delete(f"/api/lists/{mine['id']}/invites/{invite['id']}").status_code == 404
    # The id has to belong to the list in the URL, not just to the caller's account.
    assert alice.delete(f"/api/lists/{mine['id']}/invites/9999").status_code == 404
    assert bob.delete(f"/api/lists/{other['id']}/invites/{invite['id']}").status_code == 404
    assert alice.get(f"/api/lists/{mine['id']}/invites").json() != []


def test_deleting_a_list_drops_its_waiting_requests_but_not_approved_ones(alice, admin, monkeypatch, allowed, sent, db):
    monkeypatch.setattr(config, "INVITES_PER_USER", 2)
    lst = make_list(alice)
    approved = ask(alice, lst["id"], "a@example.com").json()
    ask(alice, lst["id"], "b@example.com")
    admin.post(f"/api/admin/invites/{approved['id']}/approve")

    assert alice.delete(f"/api/lists/{lst['id']}").status_code == 200
    assert admin.get("/api/admin/invites").json() == []
    kept = db.query(models.Invite).all()
    assert [(i.email, i.status, i.list_id) for i in kept] == [("a@example.com", "approved", None)]

    # Deleting the list doesn't hand the approved person's invite back.
    other = make_list(alice, "Other")
    assert ask(alice, other["id"], "c@example.com").status_code == 200
    assert ask(alice, other["id"], "d@example.com").status_code == 403


def test_refusals_name_the_person_and_say_what_to_do(alice, admin, monkeypatch, allowed, sent, let_in, sign_in):
    monkeypatch.setattr(config, "INVITES_PER_USER", 2)
    lst = make_list(alice)

    waiting = ask(alice, lst["id"], "a@example.com")
    assert waiting.status_code == 200
    repeat = ask(alice, lst["id"], "a@example.com")
    assert repeat.status_code == 409
    assert "a@example.com" in repeat.json()["detail"] and "waiting" in repeat.json()["detail"]

    assert admin.post(f"/api/admin/invites/{waiting.json()['id']}/decline").status_code == 200
    declined = ask(alice, lst["id"], "a@example.com")
    assert "declined" in declined.json()["detail"]

    sign_in("dana@example.com")  # enabled here
    let_in.add("dana@example.com")
    signs_in = ask(alice, lst["id"], "dana@example.com")
    assert "dana@example.com" in signs_in.json()["detail"] and "Add" in signs_in.json()["detail"]

    assert ask(alice, lst["id"], "b@example.com").status_code == 200
    none_left = ask(alice, lst["id"], "c@example.com")
    assert none_left.status_code == 403
    assert "2" in none_left.json()["detail"]


# --- telling the person who was let in ----------------------------------------


@pytest.fixture()
def emails(monkeypatch):
    """Stand-in for the SMTP server: what each person would be emailed."""
    mails = []
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body: mails.append((to, subject, body)) or True)
    return mails


def test_approving_emails_the_new_person_with_how_to_sign_in(alice, admin, allowed, sent, emails):
    lst = make_list(alice, "Gifts")
    invite = ask(alice, lst["id"], NEWBIE, role="edit").json()
    assert emails == []  # nothing until the administrator decides

    assert admin.post(f"/api/admin/invites/{invite['id']}/approve").status_code == 200
    assert len(emails) == 1
    to, subject, body = emails[0]
    assert to == NEWBIE
    assert alice.email in subject and "Gifts" in subject
    assert 'gave you access to the list "Gifts" in Lists - you can edit it.' in body
    assert f"{config.PUBLIC_URL}/list.html?id={lst['id']}" in body
    assert "one-time PIN" in body  # they've never signed in here
    assert f"\n    {NEWBIE}\n" in body  # the address to type on the sign-in page, on its own line


def test_an_administrators_own_request_also_emails_the_person(admin, allowed, emails):
    lst = make_list(admin)
    assert ask(admin, lst["id"], NEWBIE).status_code == 200
    assert [to for to, _, _ in emails] == [NEWBIE]


def test_declining_emails_nobody(alice, admin, allowed, sent, emails):
    lst = make_list(alice)
    invite = ask(alice, lst["id"]).json()
    assert admin.post(f"/api/admin/invites/{invite['id']}/decline").status_code == 200
    assert emails == []


def test_adding_someone_who_has_signed_in_emails_them_without_the_pin_text(alice, bob, emails):
    lst = make_list(alice)
    share(alice, lst["id"], bob, "view")
    assert [to for to, _, _ in emails] == [bob.email]
    body = emails[0][2]
    assert "you can view it" in body and f"list.html?id={lst['id']}" in body
    assert "one-time PIN" not in body


def test_a_refused_add_sends_no_email(alice, emails):
    lst = make_list(alice)
    assert alice.post(f"/api/lists/{lst['id']}/members", {"email": alice.email, "role": "view"}).status_code == 409
    assert emails == []


def test_a_failing_email_doesnt_undo_the_approval(alice, admin, allowed, sent, monkeypatch, caplog):
    def broken(to, subject, body):
        raise OSError("smtp.example.com refused user=secret-user password=hunter2")

    monkeypatch.setattr(notify, "send_email", broken)
    lst = make_list(alice)
    invite = ask(alice, lst["id"]).json()
    with caplog.at_level("WARNING"):
        resp = admin.post(f"/api/admin/invites/{invite['id']}/approve")
    assert resp.status_code == 200 and resp.json()["status"] == "approved"
    assert allowed == [NEWBIE]
    assert "OSError" in caplog.text and "hunter2" not in caplog.text and "secret-user" not in caplog.text


def test_the_apps_administrators_are_what_cloudflare_is_asked_about(alice, bob, monkeypatch):
    """Whether someone can sign in includes "they are an administrator" (they get in
    by their own policy), and which emails those are is this app's to say."""
    asked = []
    monkeypatch.setattr(cloudflare, "is_let_in", lambda email, admin_emails=(): asked.append(set(admin_emails)) or True)
    lst = make_list(alice)
    bob.get("/api/me")
    assert alice.post(f"/api/lists/{lst['id']}/members", {"email": bob.email, "role": "view"}).status_code == 200
    assert asked == [config.ADMIN_EMAILS] and config.DEV_USER_EMAIL in asked[0]
