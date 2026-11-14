"""GET /api/lists/cost-summary: what the finances app reads. Each list that tracks costs is one lump
sum (what is still to buy), counted the same way the list's own totals strip counts it. The finances
app calls with a service token and gets the administrator's lists; anyone signed in gets their own."""
import pytest

from app import config
from tests.test_access import make_item, make_list, share

URL = "/api/lists/cost-summary"
TOKEN = "s3cret-token"


@pytest.fixture()
def service(client, monkeypatch):
    """A caller with the service token, as the finances app sends it."""
    monkeypatch.setattr(config, "SERVICE_TOKEN", TOKEN)
    return lambda token=TOKEN: client.get(URL, headers={"X-Service-Token": token})


def tracked(person, name="Move to Portland"):
    lst = make_list(person, name)
    assert person.patch(f"/api/lists/{lst['id']}", {"track_costs": True}).status_code == 200
    return lst


def test_each_list_that_tracks_costs_is_one_lump_sum(admin):
    lst = tracked(admin)
    make_item(admin, lst["id"], "Bed", estimate_cents=90_000, final_cents=80_000)
    make_item(admin, lst["id"], "Lamp", estimate_cents=5_000)
    towels = make_item(admin, lst["id"], "Towels", estimate_cents=3_000)
    admin.patch(f"/api/items/{towels['id']}", {"done": True})
    make_item(admin, lst["id"], "Sofa", estimate_cents=50_000, exclude_from_totals=True)
    make_item(admin, lst["id"], "No price yet")
    make_list(admin, "Groceries")  # does not track costs: not in the summary

    rows = admin.get(URL).json()
    assert [r["name"] for r in rows] == ["Move to Portland"]
    row = rows[0]
    assert row["id"] == lst["id"]
    assert (row["total_cost_cents"], row["bought_cents"], row["to_buy_cents"]) == (88_000, 3_000, 85_000)
    assert (row["item_count"], row["open_count"], row["excluded_count"], row["unpriced_count"]) == (5, 4, 1, 1)


def test_a_person_sees_only_their_own_and_shared_lists(alice, bob):
    tracked(alice, "Alice's move")
    tracked(bob, "Bob's move")
    assert [r["name"] for r in alice.get(URL).json()] == ["Alice's move"]
    share(bob, tracked(bob, "Shared move")["id"], alice, "view")
    assert sorted(r["name"] for r in alice.get(URL).json()) == ["Alice's move", "Shared move"]


def test_the_service_token_reads_the_administrators_lists(service, admin, alice):
    tracked(admin, "Admin move")
    tracked(alice, "Alice's move")
    resp = service()
    assert resp.status_code == 200
    assert [r["name"] for r in resp.json()] == ["Admin move"]


def test_a_wrong_or_unconfigured_token_is_refused(client, service, monkeypatch):
    assert service("nope").status_code == 401
    monkeypatch.setattr(config, "SERVICE_TOKEN", None)
    assert client.get(URL, headers={"X-Service-Token": TOKEN}).status_code == 401  # unset: never matches
    assert client.get(URL, headers={"X-Service-Token": ""}).status_code == 401


def test_a_signed_out_caller_with_no_token_is_refused(client):
    # Locally an unsigned request is treated as the dev user, so check the production-shaped rule:
    # no token and no way to tell who is asking is not an open door.
    assert client.get(URL, headers={"Cf-Access-Authenticated-User-Email": "not-an-email"}).status_code == 401
