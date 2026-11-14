"""Cost tracking: a list can be set to track costs; each item then has an estimate and a final
cost (whole cents), and the list reports totals. An item counts at its final cost once that is
entered, otherwise at its estimate."""
from tests.test_access import make_item, make_list, share


def costed_list(person, **extra):
    lst = make_list(person, "Move to Portland", **extra)
    resp = person.patch(f"/api/lists/{lst['id']}", {"track_costs": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


def totals(person, list_id):
    body = person.get(f"/api/lists/{list_id}").json()
    return body["cost_total_cents"], body["cost_bought_cents"], body["unpriced_count"]


# --- the setting ---------------------------------------------------------------------


def test_a_new_list_does_not_track_costs(alice):
    lst = make_list(alice)
    assert lst["track_costs"] is False
    assert (lst["cost_total_cents"], lst["cost_bought_cents"], lst["unpriced_count"]) == (0, 0, 0)


def test_only_the_owner_can_turn_it_on_or_off(alice, bob):
    lst = make_list(alice)
    share(alice, lst["id"], bob, "edit")
    assert bob.patch(f"/api/lists/{lst['id']}", {"track_costs": True}).status_code == 403
    assert alice.patch(f"/api/lists/{lst['id']}", {"track_costs": True}).json()["track_costs"] is True
    assert bob.patch(f"/api/lists/{lst['id']}", {"track_costs": False}).status_code == 403
    assert alice.patch(f"/api/lists/{lst['id']}", {"track_costs": False}).json()["track_costs"] is False


def test_the_setting_cannot_be_cleared_to_null(alice):
    lst = make_list(alice)
    assert alice.patch(f"/api/lists/{lst['id']}", {"track_costs": None}).status_code == 400


# --- prices on items -----------------------------------------------------------------


def test_an_item_takes_an_estimate_and_a_final_cost(alice):
    lst = costed_list(alice)
    item = make_item(alice, lst["id"], estimate_cents=12500)
    assert (item["estimate_cents"], item["final_cents"], item["cost_cents"]) == (12500, None, 12500)
    updated = alice.patch(f"/api/items/{item['id']}", {"final_cents": 11000}).json()
    assert (updated["estimate_cents"], updated["final_cents"], updated["cost_cents"]) == (12500, 11000, 11000)


def test_clearing_the_final_cost_goes_back_to_the_estimate(alice):
    lst = costed_list(alice)
    item = make_item(alice, lst["id"], estimate_cents=500, final_cents=900)
    cleared = alice.patch(f"/api/items/{item['id']}", {"final_cents": None}).json()
    assert (cleared["final_cents"], cleared["cost_cents"]) == (None, 500)


def test_a_final_cost_of_zero_counts_as_entered(alice):
    # A free item (a hand-me-down) is a real answer, not "not filled in".
    lst = costed_list(alice)
    item = make_item(alice, lst["id"], estimate_cents=5000, final_cents=0)
    assert item["cost_cents"] == 0
    assert totals(alice, lst["id"]) == (0, 0, 0)


def test_a_final_cost_with_no_estimate_counts(alice):
    lst = costed_list(alice)
    make_item(alice, lst["id"], final_cents=700)
    assert totals(alice, lst["id"]) == (700, 0, 0)


def test_prices_must_be_whole_non_negative_cents(alice):
    lst = costed_list(alice)
    for bad in (-1, 1.5, "abc", 10**12):
        resp = alice.post(f"/api/lists/{lst['id']}/items", {"name": "x", "estimate_cents": bad})
        assert resp.status_code == 422, bad
    item = make_item(alice, lst["id"])
    assert alice.patch(f"/api/items/{item['id']}", {"final_cents": -5}).status_code == 422


def test_a_view_only_member_cannot_change_prices(alice, bob):
    lst = costed_list(alice)
    item = make_item(alice, lst["id"], estimate_cents=100)
    share(alice, lst["id"], bob, "view")
    assert bob.patch(f"/api/items/{item['id']}", {"estimate_cents": 1}).status_code == 403
    assert bob.get(f"/api/items/{item['id']}").json()["estimate_cents"] == 100


# --- totals --------------------------------------------------------------------------


def test_totals_use_the_final_cost_where_known_and_the_estimate_elsewhere(alice):
    lst = costed_list(alice)
    make_item(alice, lst["id"], "Couch", estimate_cents=80000, final_cents=75000)
    make_item(alice, lst["id"], "Boxes", estimate_cents=6000)
    make_item(alice, lst["id"], "Lamp")  # no price yet
    assert totals(alice, lst["id"]) == (81000, 0, 1)


def test_done_items_count_as_bought_and_the_rest_is_still_to_buy(alice):
    lst = costed_list(alice)
    couch = make_item(alice, lst["id"], "Couch", estimate_cents=80000, final_cents=75000)
    make_item(alice, lst["id"], "Boxes", estimate_cents=6000)
    alice.patch(f"/api/items/{couch['id']}", {"done": True})
    total, bought, unpriced = totals(alice, lst["id"])
    assert (total, bought, unpriced) == (81000, 75000, 0)
    assert total - bought == 6000  # still to buy, worked out by the page


def test_an_unpriced_done_item_is_still_counted_as_unpriced(alice):
    lst = costed_list(alice)
    item = make_item(alice, lst["id"], "Gift")
    alice.patch(f"/api/items/{item['id']}", {"done": True})
    assert totals(alice, lst["id"]) == (0, 0, 1)


def test_an_empty_list_totals_zero(alice):
    lst = costed_list(alice)
    assert totals(alice, lst["id"]) == (0, 0, 0)


def test_totals_are_only_reported_for_lists_that_track_costs(alice):
    lst = make_list(alice)
    make_item(alice, lst["id"], estimate_cents=1234)
    assert totals(alice, lst["id"]) == (0, 0, 0)
    alice.patch(f"/api/lists/{lst['id']}", {"track_costs": True})
    assert totals(alice, lst["id"]) == (1234, 0, 0)
    alice.patch(f"/api/lists/{lst['id']}", {"track_costs": False})
    assert totals(alice, lst["id"]) == (0, 0, 0)
    # ...and the prices were kept all along.
    assert alice.get(f"/api/lists/{lst['id']}/items").json()[0]["estimate_cents"] == 1234


def test_the_lists_index_carries_the_totals_too(alice):
    lst = costed_list(alice)
    make_item(alice, lst["id"], estimate_cents=2500)
    make_list(alice, "Plain")
    rows = {row["name"]: row for row in alice.get("/api/lists").json()}
    assert rows["Move to Portland"]["cost_total_cents"] == 2500
    assert rows["Plain"]["cost_total_cents"] == 0


def test_each_list_has_its_own_totals(alice):
    one, two = costed_list(alice), costed_list(alice)
    make_item(alice, one["id"], estimate_cents=100)
    make_item(alice, two["id"], estimate_cents=900)
    assert totals(alice, one["id"])[0] == 100
    assert totals(alice, two["id"])[0] == 900


def test_a_shared_member_sees_the_same_totals(alice, bob):
    lst = costed_list(alice)
    make_item(alice, lst["id"], estimate_cents=4200)
    share(alice, lst["id"], bob, "view")
    assert totals(bob, lst["id"]) == (4200, 0, 0)


def test_moving_an_item_moves_its_cost_with_it(alice):
    a, b = costed_list(alice), costed_list(alice)
    item = make_item(alice, a["id"], estimate_cents=300, final_cents=250)
    alice.patch(f"/api/items/{item['id']}", {"list_id": b["id"]})
    assert totals(alice, a["id"]) == (0, 0, 0)
    assert totals(alice, b["id"]) == (250, 0, 0)


def test_deleting_an_item_takes_it_out_of_the_total(alice):
    lst = costed_list(alice)
    item = make_item(alice, lst["id"], estimate_cents=300)
    alice.delete(f"/api/items/{item['id']}")
    assert totals(alice, lst["id"]) == (0, 0, 0)


# --- sorting by price ----------------------------------------------------------------


def names(person, list_id):
    return [i["name"] for i in person.get(f"/api/lists/{list_id}/items").json()]


def test_sort_by_price_puts_the_dearest_first_and_unpriced_last(alice):
    lst = costed_list(alice)
    make_item(alice, lst["id"], "cheap", estimate_cents=100)
    make_item(alice, lst["id"], "unpriced")
    make_item(alice, lst["id"], "dear", estimate_cents=900)
    make_item(alice, lst["id"], "mid-but-final-is-high", estimate_cents=200, final_cents=500)
    assert alice.patch(f"/api/lists/{lst['id']}", {"sort_mode": "price"}).json()["sort_mode"] == "price"
    assert names(alice, lst["id"]) == ["dear", "mid-but-final-is-high", "cheap", "unpriced"]


def test_done_items_still_sink_below_the_rest_when_sorting_by_price(alice):
    lst = costed_list(alice)
    big = make_item(alice, lst["id"], "big", estimate_cents=9000)
    make_item(alice, lst["id"], "small", estimate_cents=100)
    alice.patch(f"/api/items/{big['id']}", {"done": True})
    alice.patch(f"/api/lists/{lst['id']}", {"sort_mode": "price"})
    assert names(alice, lst["id"]) == ["small", "big"]


def test_sorting_by_price_needs_cost_tracking(alice):
    lst = make_list(alice)
    assert alice.patch(f"/api/lists/{lst['id']}", {"sort_mode": "price"}).status_code == 400
    # Turning tracking on in the same request is fine.
    both = alice.patch(f"/api/lists/{lst['id']}", {"track_costs": True, "sort_mode": "price"})
    assert both.status_code == 200 and both.json()["sort_mode"] == "price"


def test_turning_tracking_off_puts_the_sort_back_to_manual(alice):
    lst = costed_list(alice)
    alice.patch(f"/api/lists/{lst['id']}", {"sort_mode": "price"})
    off = alice.patch(f"/api/lists/{lst['id']}", {"track_costs": False}).json()
    assert off["sort_mode"] == "manual"


def test_an_editor_can_sort_by_price_but_not_turn_tracking_on(alice, bob):
    lst = costed_list(alice)
    share(alice, lst["id"], bob, "edit")
    assert bob.patch(f"/api/lists/{lst['id']}", {"sort_mode": "price"}).status_code == 200
    plain = make_list(alice, "Plain")
    share(alice, plain["id"], bob, "edit")
    assert bob.patch(f"/api/lists/{plain['id']}", {"sort_mode": "price"}).status_code == 400
