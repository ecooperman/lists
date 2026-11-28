"""Sorting a list's items by who they are for, A-Z or Z-A (by the contact's first name, then last)."""
from tests.test_access import make_item, make_list, share


def contact(person, first, last=None):
    resp = person.post("/api/contacts", {"first_name": first, **({"last_name": last} if last else {})})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def names(person, list_id):
    return [i["name"] for i in person.get(f"/api/lists/{list_id}/items").json()]


def gifts(alice):
    lst = make_list(alice, "Gifts")
    zed, amy, bob_smith, bob_adams = contact(alice, "zed"), contact(alice, "Amy"), contact(alice, "Bob", "Smith"), contact(alice, "Bob", "Adams")
    make_item(alice, lst["id"], "for zed", recipient_id=zed)
    make_item(alice, lst["id"], "for nobody")
    make_item(alice, lst["id"], "for amy", recipient_id=amy)
    make_item(alice, lst["id"], "for bob smith", recipient_id=bob_smith)
    make_item(alice, lst["id"], "for bob adams", recipient_id=bob_adams)
    return lst


def test_a_to_z_ignores_case_breaks_ties_by_last_name_and_puts_no_recipient_last(alice):
    lst = gifts(alice)
    assert alice.patch(f"/api/lists/{lst['id']}", {"sort_mode": "recipient"}).json()["sort_mode"] == "recipient"
    assert names(alice, lst["id"]) == ["for amy", "for bob adams", "for bob smith", "for zed", "for nobody"]


def test_z_to_a_reverses_the_people_but_still_puts_no_recipient_last(alice):
    lst = gifts(alice)
    alice.patch(f"/api/lists/{lst['id']}", {"sort_mode": "recipient_desc"})
    assert names(alice, lst["id"]) == ["for zed", "for bob smith", "for bob adams", "for amy", "for nobody"]


def test_done_items_still_sink_and_the_same_person_keeps_manual_order(alice):
    lst = make_list(alice)
    amy = contact(alice, "Amy")
    first = make_item(alice, lst["id"], "first", recipient_id=amy)
    make_item(alice, lst["id"], "second", recipient_id=amy)
    make_item(alice, lst["id"], "third", recipient_id=amy)
    assert alice.patch(f"/api/items/{first['id']}", {"done": True}).status_code == 200
    alice.patch(f"/api/lists/{lst['id']}", {"sort_mode": "recipient"})
    assert names(alice, lst["id"]) == ["second", "third", "first"]


def test_an_editor_can_pick_it_and_a_viewer_cannot(alice, bob):
    lst = gifts(alice)
    viewer_list = gifts(alice)
    share(alice, viewer_list["id"], bob, "view")
    assert bob.patch(f"/api/lists/{viewer_list['id']}", {"sort_mode": "recipient"}).status_code == 403
    share(alice, lst["id"], bob, "edit")
    assert bob.patch(f"/api/lists/{lst['id']}", {"sort_mode": "recipient_desc"}).status_code == 200
    assert names(bob, lst["id"])[0] == "for zed"


def test_an_unknown_sort_is_refused(alice):
    lst = make_list(alice)
    assert alice.patch(f"/api/lists/{lst['id']}", {"sort_mode": "colour"}).status_code == 422
