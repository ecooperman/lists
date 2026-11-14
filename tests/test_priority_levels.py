"""A list can hide some of the five priority levels from its pickers (a shopping list that
only wants three). Hiding is only about what can be chosen: items keep what they have, and
sorting is untouched."""
from tests.test_access import make_item, make_list, share


def test_a_new_list_hides_nothing(alice):
    assert make_list(alice)["hidden_priorities"] == []


def test_the_owner_can_hide_levels_and_the_choice_is_saved(alice):
    lst = make_list(alice)
    resp = alice.patch(f"/api/lists/{lst['id']}", {"hidden_priorities": [5, 1, 5]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["hidden_priorities"] == [1, 5]
    assert alice.get(f"/api/lists/{lst['id']}").json()["hidden_priorities"] == [1, 5]
    assert alice.patch(f"/api/lists/{lst['id']}", {"hidden_priorities": []}).json()["hidden_priorities"] == []


def test_hiding_every_level_switches_priority_off_but_only_while_no_item_has_one(alice):
    lst = make_list(alice)
    url = f"/api/lists/{lst['id']}"
    item = make_item(alice, lst["id"], "Bed")
    assert alice.patch(f"/api/items/{item['id']}", {"priority": 2}).status_code == 200
    refused = alice.patch(url, {"hidden_priorities": [1, 2, 3, 4, 5]})
    assert refused.status_code == 400 and "1 item has a priority" in refused.json()["detail"]
    assert alice.get(url).json()["hidden_priorities"] == []  # nothing changed

    assert alice.patch(f"/api/items/{item['id']}", {"priority": None}).status_code == 200
    assert alice.patch(url, {"hidden_priorities": [1, 2, 3, 4, 5]}).json()["hidden_priorities"] == [1, 2, 3, 4, 5]


def test_priority_sort_is_refused_and_reset_when_every_level_is_hidden(alice):
    lst = make_list(alice)
    url = f"/api/lists/{lst['id']}"
    assert alice.patch(url, {"sort_mode": "priority"}).status_code == 200
    # Hiding every level drops a list that was sorted by priority back to manual order...
    assert alice.patch(url, {"hidden_priorities": [1, 2, 3, 4, 5]}).json()["sort_mode"] == "manual"
    # ...and won't go back to priority while it is off.
    assert alice.patch(url, {"sort_mode": "priority"}).status_code == 400
    assert alice.patch(url, {"hidden_priorities": [1, 2]}).status_code == 200
    assert alice.patch(url, {"sort_mode": "priority"}).status_code == 200


def test_bad_hidden_priority_values_are_refused(alice):
    lst = make_list(alice)
    url = f"/api/lists/{lst['id']}"
    assert alice.patch(url, {"hidden_priorities": None}).status_code == 400
    assert alice.patch(url, {"hidden_priorities": [0]}).status_code == 422
    assert alice.patch(url, {"hidden_priorities": [6]}).status_code == 422


def test_only_the_owner_can_hide_levels(alice, bob):
    lst = make_list(alice)
    share(alice, lst["id"], bob, "edit")
    assert bob.patch(f"/api/lists/{lst['id']}", {"hidden_priorities": [1]}).status_code == 403


def test_items_keep_a_level_that_is_hidden_afterwards(alice):
    lst = make_list(alice)
    item = make_item(alice, lst["id"], "Bed")
    assert alice.patch(f"/api/items/{item['id']}", {"priority": 4}).status_code == 200
    assert alice.patch(f"/api/lists/{lst['id']}", {"hidden_priorities": [4]}).status_code == 200
    assert alice.get(f"/api/items/{item['id']}").json()["priority"] == 4


def test_labels_and_hidden_levels_are_independent(alice):
    lst = make_list(alice)
    url = f"/api/lists/{lst['id']}"
    body = alice.patch(url, {"priority_labels": ["Want", "", "Need", "", "Required"], "hidden_priorities": [2, 4]}).json()
    assert body["priority_labels"] == ["Want", "Medium", "Need", "Critical", "Required"]
    assert body["hidden_priorities"] == [2, 4]
    # Resetting the names leaves the hidden levels alone.
    assert alice.patch(url, {"priority_labels": None}).json()["hidden_priorities"] == [2, 4]
