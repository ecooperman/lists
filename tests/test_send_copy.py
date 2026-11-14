"""Send a copy: a list or an item rendered as text and rich text to paste
elsewhere. Anyone who can see the list can make one; what is in it is only what
was asked for, and never who the list is shared with or a contact's details."""
from tests.test_access import make_item, make_list, share


def link(url, label=None):
    return {"label": label, "url": url}


def copy_list(person, list_id, **options):
    resp = person.post(f"/api/lists/{list_id}/copy", options)
    assert resp.status_code == 200, resp.text
    return resp.json()


def copy_item(person, item_id, **options):
    resp = person.post(f"/api/items/{item_id}/copy", options)
    assert resp.status_code == 200, resp.text
    return resp.json()


def portland(alice):
    lst = make_list(alice, "Portland")
    a = make_item(alice, lst["id"], "Apartment A", links=[link("https://a.example/listing", "Listing"), link("https://a.example/reviews")])
    b = make_item(alice, lst["id"], "Coffee shop")
    return lst, a, b


# --- the text -----------------------------------------------------------------------


def test_the_default_is_a_bulleted_list_with_the_list_name_and_links(alice):
    lst, _, _ = portland(alice)
    result = copy_list(alice, lst["id"])
    assert result["text"] == (
        "Portland\n\n"
        "- Apartment A\n"
        "  Listing: https://a.example/listing\n"
        "  https://a.example/reviews\n"
        "\n"
        "- Coffee shop"
    )
    assert result["count"] == 2


def test_names_only_is_a_tight_list(alice):
    lst, _, _ = portland(alice)
    result = copy_list(alice, lst["id"], links=False, heading=False)
    assert result["text"] == "- Apartment A\n- Coffee shop"


def test_numbered_checkbox_and_plain_layouts(alice):
    lst, a, _ = portland(alice)
    numbered = copy_list(alice, lst["id"], links=False, heading=False, style="numbered")["text"]
    assert numbered == "1. Apartment A\n2. Coffee shop"
    boxes = copy_list(alice, lst["id"], links=False, heading=False, style="checkboxes")["text"]
    assert boxes == "☐ Apartment A\n☐ Coffee shop"
    plain = copy_list(alice, lst["id"], links=False, heading=False, style="plain")["text"]
    assert plain == "Apartment A\nCoffee shop"
    alice.patch(f"/api/items/{a['id']}", {"done": True})
    assert copy_list(alice, lst["id"], links=False, heading=False, style="checkboxes")["text"] == "☐ Coffee shop\n☑ Apartment A"


def test_each_detail_appears_only_when_asked_for(alice):
    lst = make_list(alice, "Gifts")
    contact = alice.post("/api/contacts", {"first_name": "Zed", "last_name": "Smith", "email": "zed@example.com", "address": "1 Main St"}).json()
    item = make_item(
        alice, lst["id"], "Watch", description="Steel one\nwith a blue face", needed_by="2026-12-25T00:00:00",
        priority=3, recipient_id=contact["id"], links=[link("https://shop.example/watch", "Shop")],
    )
    alice.patch(f"/api/items/{item['id']}", {"progress": 40})

    bare = copy_list(alice, lst["id"], links=False, heading=False)["text"]
    assert bare == "- Watch"

    full = copy_list(
        alice, lst["id"], heading=False, description=True, needed_by=True, priority=True, progress=True, recipient=True
    )["text"]
    assert full == (
        "- Watch\n"
        "  Steel one\n"
        "  with a blue face\n"
        "  Shop: https://shop.example/watch\n"
        "  Needed by: Dec 25, 2026\n"
        "  Priority: High\n"
        "  Progress: 40%\n"
        "  For: Zed Smith"
    )
    # Only the contact's name: never the address book entry's other details.
    assert "zed@example.com" not in full and "Main St" not in full


def test_priority_uses_the_lists_own_labels(alice):
    lst = make_list(alice, "Chores")
    assert alice.patch(f"/api/lists/{lst['id']}", {"priority_labels": ["Meh", "", "", "", "Now!"]}).status_code == 200
    make_item(alice, lst["id"], "Dishes", priority=5)
    assert "Priority: Now!" in copy_list(alice, lst["id"], links=False, priority=True)["text"]


def test_progress_is_left_out_for_done_and_untouched_items(alice):
    lst = make_list(alice)
    started = make_item(alice, lst["id"], "Started")
    done = make_item(alice, lst["id"], "Finished")
    make_item(alice, lst["id"], "Untouched")
    alice.patch(f"/api/items/{started['id']}", {"progress": 50})
    alice.patch(f"/api/items/{done['id']}", {"progress": 80, "done": True})
    text = copy_list(alice, lst["id"], links=False, heading=False, progress=True)["text"]
    assert text.count("Progress:") == 1 and "Progress: 50%" in text


def test_done_items_can_be_shown_hidden_or_marked(alice):
    lst, a, _ = portland(alice)
    alice.patch(f"/api/items/{a['id']}", {"done": True})
    base = dict(links=False, heading=False)
    assert copy_list(alice, lst["id"], done="show", **base)["text"] == "- Coffee shop\n- Apartment A"
    assert copy_list(alice, lst["id"], done="strike", **base)["text"] == "- Coffee shop\n- Apartment A (done)"
    hidden = copy_list(alice, lst["id"], done="hide", **base)
    assert hidden["text"] == "- Coffee shop" and hidden["count"] == 1


def test_order_is_the_lists_own_unless_priority_is_asked_for(alice):
    lst = make_list(alice)
    make_item(alice, lst["id"], "Low one", priority=1)
    make_item(alice, lst["id"], "No priority")
    make_item(alice, lst["id"], "Top one", priority=5)
    base = dict(links=False, heading=False)
    assert copy_list(alice, lst["id"], **base)["text"] == "- Low one\n- No priority\n- Top one"
    assert copy_list(alice, lst["id"], order="priority", **base)["text"] == "- Top one\n- Low one\n- No priority"


def test_done_items_stay_last_when_ordering_by_priority(alice):
    lst = make_list(alice)
    finished = make_item(alice, lst["id"], "Finished top priority", priority=5)
    make_item(alice, lst["id"], "Open low", priority=1)
    alice.patch(f"/api/items/{finished['id']}", {"done": True})
    text = copy_list(alice, lst["id"], order="priority", links=False, heading=False)["text"]
    assert text == "- Open low\n- Finished top priority"


def test_an_empty_list_says_so(alice):
    lst = make_list(alice, "Empty")
    assert copy_list(alice, lst["id"])["text"] == "Empty\n\n(no items)"
    assert copy_list(alice, lst["id"], heading=False)["text"] == "(no items)"


# --- the rich version ----------------------------------------------------------------


def test_the_rich_version_links_the_label_or_the_address(alice):
    lst, _, _ = portland(alice)
    html = copy_list(alice, lst["id"])["html"]
    assert html.startswith("<h3>Portland</h3><ul>")
    assert '<a href="https://a.example/listing">Listing</a>' in html
    assert '<a href="https://a.example/reviews">a.example</a>' in html  # no label: the site, not the long address
    assert "<ol>" in copy_list(alice, lst["id"], style="numbered")["html"]


def test_an_unlabelled_link_shows_the_site_in_the_rich_version_but_the_address_in_the_text(alice):
    lst = make_list(alice, "Eat")
    long = "https://www.opentable.com/booking/restref/availability?rid=1&lang=en-US&otSource=Restaurant%20website"
    make_item(alice, lst["id"], "Kasama", links=[link(long)])
    result = copy_list(alice, lst["id"])
    assert f'<a href="{long.replace("&", "&amp;")}">opentable.com</a>' in result["html"]
    assert long in result["text"]


def test_everything_typed_by_people_is_escaped_in_the_rich_version(alice):
    lst = make_list(alice, "<script>alert(1)</script>")
    make_item(alice, lst["id"], "<img src=x onerror=alert(1)>", description="a <b>bold</b> & more", links=[link("https://x.example/?a=1&b=2\"onmouseover=\"x", '"><svg>')])
    html = copy_list(alice, lst["id"], description=True)["html"]
    for raw in ("<script>", "<img", "<b>bold</b>", "<svg>", '"onmouseover="x'):
        assert raw not in html
    assert "&lt;script&gt;" in html and "&amp; more" in html


def test_strike_is_drawn_in_the_rich_version_and_noted_in_the_text(alice):
    lst, a, _ = portland(alice)
    alice.patch(f"/api/items/{a['id']}", {"done": True})
    result = copy_list(alice, lst["id"], done="strike", links=False)
    assert "<s>Apartment A</s>" in result["html"] and "Apartment A (done)" in result["text"]


# --- one item ------------------------------------------------------------------------


def test_copying_one_item_gives_just_its_links(alice):
    _, a, _ = portland(alice)
    result = copy_item(alice, a["id"], style="plain")
    assert result["text"] == "Apartment A\nListing: https://a.example/listing\nhttps://a.example/reviews"
    assert result["count"] == 1 and "<h3>" not in result["html"]


def test_an_items_copy_follows_the_lists_priority_labels(alice):
    lst = make_list(alice)
    assert alice.patch(f"/api/lists/{lst['id']}", {"priority_labels": ["", "", "Soonish", "", ""]}).status_code == 200
    item = make_item(alice, lst["id"], "Thing", priority=3)
    assert "Priority: Soonish" in copy_item(alice, item["id"], priority=True)["text"]


# --- who can ----------------------------------------------------------------------------


def test_view_only_members_can_copy_but_strangers_cant(alice, bob, carol):
    lst, a, _ = portland(alice)
    share(alice, lst["id"], bob, "view")
    assert "Apartment A" in copy_list(bob, lst["id"])["text"]
    assert "Apartment A" in copy_item(bob, a["id"])["text"]
    assert carol.post(f"/api/lists/{lst['id']}/copy", {}).status_code == 404
    assert carol.post(f"/api/items/{a['id']}/copy", {}).status_code == 404


def test_a_copy_never_mentions_who_the_list_is_shared_with(alice, bob):
    lst, _, _ = portland(alice)
    share(alice, lst["id"], bob, "edit")
    result = copy_list(alice, lst["id"], description=True, needed_by=True, priority=True, progress=True, recipient=True)
    assert bob.email not in result["text"] + result["html"]
    assert alice.email not in result["text"] + result["html"]


def test_a_stranger_without_an_account_cant_copy(sign_in, alice):
    lst, _, _ = portland(alice)
    nobody = sign_in("nobody@example.com", enabled=False)
    assert nobody.post(f"/api/lists/{lst['id']}/copy", {}).status_code == 403


def test_options_are_checked(alice):
    lst, _, _ = portland(alice)
    for bad in ({"style": "fancy"}, {"done": "maybe"}, {"order": "random"}, {"links": "sometimes"}):
        assert alice.post(f"/api/lists/{lst['id']}/copy", bad).status_code == 422


# --- by email -------------------------------------------------------------------------

import pytest  # noqa: E402

from app import config, notify  # noqa: E402


@pytest.fixture()
def mails(monkeypatch):
    """Every email the app tries to send: (to, subject, text, html, reply_to)."""
    sent = []

    def fake(to, subject, body, html=None, reply_to=None):
        sent.append((to, subject, body, html, reply_to))
        return True

    monkeypatch.setattr(notify, "send_email", fake)
    return sent


def email_list(person, list_id, to="friend@example.com", **options):
    return person.post(f"/api/lists/{list_id}/email", {"to": to, **options})


def test_emailing_a_copy_sends_what_the_copy_says_with_replies_to_the_sender(alice, mails):
    lst, _, _ = portland(alice)
    resp = email_list(alice, lst["id"], to="Friend@Example.com")
    assert resp.status_code == 200, resp.text
    assert resp.json()["sent_to"] == "friend@example.com"
    ((to, subject, text, html, reply_to),) = mails
    assert to == "friend@example.com" and reply_to == alice.email
    assert alice.email in subject and "Portland" in subject
    assert text.startswith(copy_list(alice, lst["id"])["text"])
    assert "Apartment A" in html and "<a " in html
    assert alice.email in text and alice.email in html  # it says who it is from


def test_the_email_follows_the_chosen_options(alice, mails):
    lst, _, _ = portland(alice)
    email_list(alice, lst["id"], style="numbered", links=False, heading=False)
    assert mails[0][2].startswith("1. Apartment A\n2. Coffee shop")


def test_what_is_typed_into_a_list_is_escaped_in_the_email(alice, mails):
    lst = make_list(alice, "<b>Bold</b> & co")
    make_item(alice, lst["id"], "<script>alert(1)</script>")
    email_list(alice, lst["id"])
    html = mails[0][3]
    assert "<script>" not in html and "<b>Bold</b>" not in html
    assert "&lt;script&gt;" in html


def test_view_only_members_can_email_but_strangers_cant(alice, bob, carol, mails):
    lst, _, _ = portland(alice)
    share(alice, lst["id"], bob, "view")
    assert email_list(bob, lst["id"]).status_code == 200
    assert mails[0][4] == bob.email
    assert email_list(carol, lst["id"]).status_code == 404
    assert len(mails) == 1


def test_a_stranger_without_an_account_cant_email(sign_in, alice, mails):
    lst, _, _ = portland(alice)
    nobody = sign_in("nobody@example.com", enabled=False)
    assert email_list(nobody, lst["id"]).status_code == 403
    assert mails == []


def test_the_recipient_must_be_an_email_address_and_nothing_is_sent_otherwise(alice, mails):
    lst, _, _ = portland(alice)
    for bad in ("not an address", "a@b", "x@example.com\nBcc: y@example.com", ""):
        assert email_list(alice, lst["id"], to=bad).status_code in (400, 422), bad
    assert mails == []


def test_a_daily_allowance_limits_how_many_can_be_emailed(alice, mails, monkeypatch):
    monkeypatch.setattr(config, "COPY_EMAILS_PER_DAY", 2)
    lst, _, _ = portland(alice)
    first = email_list(alice, lst["id"])
    assert first.json()["left_today"] == 1
    assert email_list(alice, lst["id"]).json()["left_today"] == 0
    refused = email_list(alice, lst["id"])
    assert refused.status_code == 429 and "limit" in refused.json()["detail"]
    assert len(mails) == 2


def test_the_allowance_is_per_person_and_resets_after_a_day(alice, bob, mails, monkeypatch, db):
    from datetime import datetime, timedelta

    from app import models

    monkeypatch.setattr(config, "COPY_EMAILS_PER_DAY", 1)
    lst, _, _ = portland(alice)
    share(alice, lst["id"], bob, "view")
    assert email_list(alice, lst["id"]).status_code == 200
    assert email_list(alice, lst["id"]).status_code == 429
    assert email_list(bob, lst["id"]).status_code == 200  # bob's own allowance
    db.query(models.CopyEmail).update({models.CopyEmail.sent_at: datetime.utcnow() - timedelta(days=1, minutes=1)})
    db.commit()
    assert email_list(alice, lst["id"]).status_code == 200


def test_the_administrator_has_no_daily_limit(admin, mails, monkeypatch):
    monkeypatch.setattr(config, "COPY_EMAILS_PER_DAY", 1)
    lst, _, _ = portland(admin)
    for _ in range(3):
        resp = email_list(admin, lst["id"])
        assert resp.status_code == 200 and resp.json()["left_today"] is None


def test_a_failed_or_unconfigured_send_is_reported_and_doesnt_use_the_allowance(alice, monkeypatch, db):
    from app import models

    lst, _, _ = portland(alice)
    monkeypatch.setattr(notify, "send_email", lambda *a, **k: False)  # no mail server set up
    assert email_list(alice, lst["id"]).status_code == 503

    def broken(*a, **k):
        raise OSError("connection refused: smtp.secret.example")

    monkeypatch.setattr(notify, "send_email", broken)
    resp = email_list(alice, lst["id"])
    assert resp.status_code == 502 and "secret" not in resp.text
    assert db.query(models.CopyEmail).count() == 0


def test_only_the_sender_and_time_are_kept(alice, mails, db):
    from app import models

    lst, _, _ = portland(alice)
    email_list(alice, lst["id"])
    (row,) = db.query(models.CopyEmail).all()
    assert {c.name for c in models.CopyEmail.__table__.columns} == {"id", "user_id", "sent_at"}
    assert row.sent_at is not None


def test_the_email_never_mentions_who_the_list_is_shared_with(alice, bob, mails):
    lst, _, _ = portland(alice)
    share(alice, lst["id"], bob, "edit")
    email_list(alice, lst["id"], description=True, needed_by=True, priority=True, progress=True, recipient=True)
    assert bob.email not in mails[0][2] + mails[0][3]


def test_the_note_at_the_end_is_escaped_in_the_rich_version():
    from app import schemas, sendcopy

    _, text, html = sendcopy.email_message("a<i>b</i>@example.com", "L", schemas.CopyResult(text="x", html="<p>x</p>", count=1))
    assert "<i>" not in html and "&lt;i&gt;" in html
    assert "a<i>b</i>@example.com" in text


def test_deleting_a_removed_persons_data_clears_their_email_count(admin, alice, mails, db):
    from app import crud, models

    lst, _, _ = portland(alice)
    email_list(alice, lst["id"])
    user = crud.get_account(db, alice.email)
    crud.delete_user_data(db, user)
    assert db.query(models.CopyEmail).count() == 0


# --- prices (a list that tracks costs) ---------------------------------------------------


def priced_list(alice):
    lst = make_list(alice, "Move")
    alice.patch(f"/api/lists/{lst['id']}", {"track_costs": True})
    make_item(alice, lst["id"], "Couch", estimate_cents=80000, final_cents=75000)
    make_item(alice, lst["id"], "Boxes", estimate_cents=6050)
    make_item(alice, lst["id"], "Lamp")
    return lst


def test_prices_are_left_out_unless_asked_for(alice):
    lst = priced_list(alice)
    text = copy_list(alice, lst["id"], heading=False)["text"]
    assert "$" not in text and "Total" not in text


def test_prices_show_each_items_counted_cost_and_a_total(alice):
    lst = priced_list(alice)
    text = copy_list(alice, lst["id"], heading=False, prices=True)["text"]
    assert text == (
        "- Couch\n"
        "  Price: $750\n"
        "\n"
        "- Boxes\n"
        "  Price: $60.50\n"
        "\n"
        "- Lamp\n"
        "\n"
        "Total: $810.50 (1 without a price)"
    )


def test_the_total_covers_only_the_items_copied(alice):
    lst = priced_list(alice)
    couch = alice.get(f"/api/lists/{lst['id']}/items").json()[0]
    alice.patch(f"/api/items/{couch['id']}", {"done": True})
    text = copy_list(alice, lst["id"], heading=False, prices=True, done="hide")["text"]
    assert "Couch" not in text
    assert text.endswith("Total: $60.50 (1 without a price)")


def test_no_prices_means_no_total_line(alice):
    lst = make_list(alice, "Move")
    alice.patch(f"/api/lists/{lst['id']}", {"track_costs": True})
    make_item(alice, lst["id"], "Lamp")
    text = copy_list(alice, lst["id"], heading=False, prices=True)["text"]
    assert text == "- Lamp"


def test_the_rich_version_has_the_prices_and_total_too(alice):
    lst = priced_list(alice)
    html = copy_list(alice, lst["id"], heading=False, prices=True)["html"]
    assert "Price: $750" in html
    assert "<p><strong>Total:</strong> $810.50 (1 without a price)</p>" in html


def test_a_one_item_copy_can_carry_its_price(alice):
    lst = priced_list(alice)
    couch = alice.get(f"/api/lists/{lst['id']}/items").json()[0]
    text = copy_item(alice, couch["id"], style="plain", heading=False, links=False, prices=True)["text"]
    assert text == "Couch\nPrice: $750"  # no total for a single item


def test_an_emailed_copy_carries_the_prices_and_total(alice, mails):
    lst = priced_list(alice)
    assert email_list(alice, lst["id"], prices=True).status_code == 200
    to, subject, body, html, reply_to = mails[0]
    assert "Price: $750" in body and "Total: $810.50" in body
    assert "Total:</strong> $810.50" in html


def test_a_list_with_one_priced_item_has_no_total_line(alice):
    lst = make_list(alice, "Move")
    alice.patch(f"/api/lists/{lst['id']}", {"track_costs": True})
    make_item(alice, lst["id"], "Couch", estimate_cents=100)
    assert copy_list(alice, lst["id"], heading=False, prices=True)["text"] == "- Couch\n  Price: $1"


def test_big_amounts_are_written_with_thousands_separators(alice):
    lst = make_list(alice, "Move")
    alice.patch(f"/api/lists/{lst['id']}", {"track_costs": True})
    make_item(alice, lst["id"], "Car", estimate_cents=1234500)
    make_item(alice, lst["id"], "Bike", estimate_cents=99900)
    text = copy_list(alice, lst["id"], heading=False, prices=True)["text"]
    assert "Price: $12,345" in text and text.endswith("Total: $13,344")
