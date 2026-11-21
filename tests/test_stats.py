"""The numbers the dashboard's stats pages read: administrators only, counts and dates only, everyone's accounts."""
from app import models
from app.database import SessionLocal
from tests.test_access import make_item, make_list, share


def test_only_the_administrator_can_read_the_stats(alice, admin):
    assert alice.get("/api/admin/stats").status_code == 403
    assert admin.get("/api/admin/stats").status_code == 200


def test_the_stats_count_each_persons_lists_and_items_without_showing_any_of_them(admin, alice, bob):
    mine = make_list(alice, "SECRET LIST")
    make_item(alice, mine["id"], "SECRET ITEM")
    make_item(alice, mine["id"], "another")
    share(alice, mine["id"], bob, "view")
    body = admin.get("/api/admin/stats")
    accounts = {a["email"]: a for a in body.json()["accounts"]}
    assert accounts["alice@example.com"]["counts"]["lists"] == 1 and accounts["alice@example.com"]["counts"]["items on their lists"] == 2
    assert accounts["bob@example.com"]["counts"]["lists"] == 0 and accounts["bob@example.com"]["counts"]["lists shared with them"] == 1
    assert accounts["alice@example.com"]["last_activity_at"] is not None
    assert "SECRET LIST" not in body.text and "SECRET ITEM" not in body.text


def test_using_the_app_notes_when_a_person_was_last_seen(alice, db):
    assert alice.get("/api/lists").status_code == 200
    user = db.query(models.User).filter(models.User.email == "alice@example.com").one()
    assert user.active_days == 1 and user.last_seen_at is not None
