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


def test_at_least_one_level_must_stay_visible(alice):
    lst = make_list(alice)
    url = f"/api/lists/{lst['id']}"
    assert alice.patch(url, {"hidden_priorities": [1, 2, 3, 4, 5]}).status_code == 400
    assert alice.patch(url, {"hidden_priorities": [1, 2, 3, 4]}).status_code == 200
    assert alice.patch(url, {"hidden_priorities": None}).status_code == 400
    assert alice.patch(url, {"hidden_priorities": [0]}).status_code == 422
    assert alice.patch(url, {"hidden_priorities": [6]}).status_code == 422
    assert alice.get(url).json()["hidden_priorities"] == [1, 2, 3, 4]  # the bad ones changed nothing


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
