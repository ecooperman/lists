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


def test_the_dashboards_account_check_is_not_the_person_being_here(alice, db):
    plain = alice.headers
    alice.headers = {**plain, "X-Brassworks-Probe": "1"}
    assert alice.get("/api/me").status_code == 200
    alice.headers = plain
    user = db.query(models.User).filter(models.User.email == "alice@example.com").one()
    assert user.last_seen_at is None and not user.active_days  # the dashboard looking is not use
    assert alice.get("/api/me").status_code == 200
    db.expire_all()
    assert db.query(models.User).filter(models.User.email == "alice@example.com").one().active_days == 1  # but the person is


def test_a_persons_first_visit_of_the_day_is_reported_to_the_dashboard_as_lists(alice, monkeypatch):
    """So the Usage page's daily chart has a count for Lists (shared_python.usage.LastSeen(app=...))."""
    from shared_python import settings, usage

    told = []
    monkeypatch.setattr(settings, "DASHBOARD_API_BASE", "http://127.0.0.1:8090")
    monkeypatch.setattr(usage, "_send_active_day", lambda app, email, day: told.append((app, email, day)))
    monkeypatch.setattr(usage.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    assert alice.get("/api/lists").status_code == 200
    assert alice.get("/api/lists").status_code == 200
    assert [(app, email) for app, email, _day in told] == [("lists", "alice@example.com")]  # once, not per request
