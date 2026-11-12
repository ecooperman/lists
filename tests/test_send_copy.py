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
    assert '<a href="https://a.example/reviews">https://a.example/reviews</a>' in html
    assert "<ol>" in copy_list(alice, lst["id"], style="numbered")["html"]


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
