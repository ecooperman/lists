"""Several labelled links per item, and each person's own list of link labels
(the choices in the dropdown). Links are plain text on the item - shared with
everyone the list is - so the label list is only ever a convenience for the
person picking."""
import logging
import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app import models
from app.database import SessionLocal

from tests.test_access import make_item, make_list, share

ROOT = Path(__file__).resolve().parent.parent


def link(url, label=None):
    return {"label": label, "url": url}


# --- an item's links ---------------------------------------------------------------


def test_an_item_can_have_several_labelled_links_in_order(alice):
    lst = make_list(alice)
    item = make_item(
        alice, lst["id"], links=[link("https://a.example/menu", "Menu"), link("https://b.example"), link("https://c.example", "Map")]
    )
    assert item["links"] == [
        {"label": "Menu", "url": "https://a.example/menu"},
        {"label": None, "url": "https://b.example"},
        {"label": "Map", "url": "https://c.example"},
    ]
    # Whatever is read back is in the same order, from the list too.
    listed = alice.get(f"/api/lists/{lst['id']}/items").json()[0]
    assert [l["url"] for l in listed["links"]] == ["https://a.example/menu", "https://b.example", "https://c.example"]


def test_url_is_the_first_links_address_and_null_without_links(alice):
    lst = make_list(alice)
    assert make_item(alice, lst["id"])["url"] is None
    item = make_item(alice, lst["id"], links=[link("https://first.example"), link("https://second.example")])
    assert item["url"] == "https://first.example"
    alice.patch(f"/api/items/{item['id']}", {"links": []})
    assert alice.get(f"/api/items/{item['id']}").json()["url"] is None


def test_sending_links_replaces_them_and_leaving_them_out_changes_nothing(alice):
    lst = make_list(alice)
    item = make_item(alice, lst["id"], links=[link("https://a.example"), link("https://b.example")])
    iid = item["id"]

    resp = alice.patch(f"/api/items/{iid}", {"name": "Renamed"})  # no links in the request
    assert [l["url"] for l in resp.json()["links"]] == ["https://a.example", "https://b.example"]

    resp = alice.patch(f"/api/items/{iid}", {"links": [link("https://b.example", "Second"), link("https://c.example")]})
    assert resp.json()["links"] == [
        {"label": "Second", "url": "https://b.example"},
        {"label": None, "url": "https://c.example"},
    ]

    assert alice.patch(f"/api/items/{iid}", {"links": []}).json()["links"] == []
    assert alice.patch(f"/api/items/{iid}", {"links": None}).status_code == 200  # null is "no change", not "clear"


def test_only_web_addresses_are_accepted(alice):
    lst = make_list(alice)
    item = make_item(alice, lst["id"])
    for bad in ("javascript:alert(1)", "mailto:a@b.example", "ftp://x.example", "www.example.com", "", "   ", "https://", "data:text/html,hi"):
        resp = alice.patch(f"/api/items/{item['id']}", {"links": [link(bad)]})
        assert resp.status_code == 422, bad
        assert alice.post(f"/api/lists/{lst['id']}/items", {"name": "X", "links": [link(bad)]}).status_code == 422, bad
    assert alice.get(f"/api/items/{item['id']}").json()["links"] == []  # a refused request changed nothing


def test_links_are_tidied_and_limited(alice):
    lst = make_list(alice)
    item = make_item(alice, lst["id"], links=[{"label": "  Menu  ", "url": "  HTTPS://A.example/x  "}, {"label": "   ", "url": "http://b.example"}])
    assert item["links"] == [
        {"label": "Menu", "url": "HTTPS://A.example/x"},  # spaces trimmed, the address otherwise untouched
        {"label": None, "url": "http://b.example"},  # a blank label is no label
    ]
    iid = item["id"]
    assert alice.patch(f"/api/items/{iid}", {"links": [link("https://a.example", "x" * 41)]}).status_code == 422
    assert alice.patch(f"/api/items/{iid}", {"links": [link("https://a.example/" + "x" * 2000)]}).status_code == 422
    twenty = [link(f"https://a.example/{n}") for n in range(20)]
    assert alice.patch(f"/api/items/{iid}", {"links": twenty}).status_code == 200
    assert alice.patch(f"/api/items/{iid}", {"links": twenty + [link("https://a.example/more")]}).status_code == 422


def test_the_old_single_url_field_is_ignored_on_the_way_in(alice):
    lst = make_list(alice)
    item = make_item(alice, lst["id"], url="https://old-style.example")
    assert item["links"] == [] and item["url"] is None
    assert alice.patch(f"/api/items/{item['id']}", {"url": "https://old-style.example"}).json()["links"] == []


def test_view_only_members_see_links_but_cant_change_them(alice, bob):
    lst = make_list(alice)
    item = make_item(alice, lst["id"], links=[link("https://a.example", "Menu")])
    share(alice, lst["id"], bob, "view")
    assert bob.get(f"/api/items/{item['id']}").json()["links"] == [{"label": "Menu", "url": "https://a.example"}]
    assert bob.patch(f"/api/items/{item['id']}", {"links": []}).status_code == 403
    assert alice.get(f"/api/items/{item['id']}").json()["links"] != []


def test_an_editor_can_label_links_with_words_that_are_not_in_the_owners_list(alice, bob):
    lst = make_list(alice)
    item = make_item(alice, lst["id"])
    share(alice, lst["id"], bob, "edit")
    resp = bob.patch(f"/api/items/{item['id']}", {"links": [link("https://a.example", "Bob's own wording")]})
    assert resp.status_code == 200
    assert alice.get(f"/api/items/{item['id']}").json()["links"][0]["label"] == "Bob's own wording"


# --- the preview follows the first link --------------------------------------------


def _fake_preview(item_id):
    with SessionLocal() as session:
        item = session.get(models.Item, item_id)
        item.scrape_status = models.ScrapeStatus.success
        item.scraped_title = "A title"
        item.scraped_image_url = "https://img.example/a.png"
        session.commit()


def test_fetching_a_preview_uses_the_first_link(alice, monkeypatch):
    from app.routers import items as items_router

    fetched = []
    monkeypatch.setattr(items_router, "scrape_item", lambda db, item_id, url: fetched.append(url) or db.get(models.Item, item_id))
    lst = make_list(alice)
    item = make_item(alice, lst["id"], links=[link("https://first.example"), link("https://second.example")])
    assert alice.post(f"/api/items/{item['id']}/scrape").status_code == 200
    assert fetched == ["https://first.example"]


def test_a_preview_needs_a_link(alice):
    lst = make_list(alice)
    item = make_item(alice, lst["id"])
    assert alice.post(f"/api/items/{item['id']}/scrape").status_code == 400


def test_a_new_first_link_discards_the_preview_but_other_edits_keep_it(alice):
    lst = make_list(alice)
    item = make_item(alice, lst["id"], links=[link("https://first.example"), link("https://second.example")])
    iid = item["id"]
    _fake_preview(iid)

    # Changing a later link, adding one, or relabelling leaves the primary link - and its preview - alone.
    for links in (
        [link("https://first.example"), link("https://other.example")],
        [link("https://first.example"), link("https://other.example"), link("https://third.example")],
        [link("https://first.example", "Menu"), link("https://other.example")],
    ):
        assert alice.patch(f"/api/items/{iid}", {"links": links}).json()["scrape_status"] == "success"
    assert alice.patch(f"/api/items/{iid}", {"name": "Renamed"}).json()["scraped_title"] == "A title"

    # Making a different link the first one (here by reordering) discards it.
    resp = alice.patch(f"/api/items/{iid}", {"links": [link("https://other.example"), link("https://first.example")]}).json()
    assert resp["scrape_status"] == "not_started"
    assert resp["scraped_title"] is None and resp["scraped_image_url"] is None

    _fake_preview(iid)
    assert alice.patch(f"/api/items/{iid}", {"links": []}).json()["scrape_status"] == "not_started"


# --- links go when what they belong to goes ----------------------------------------


def _link_count(db):
    return db.query(models.ItemLink).count()


def test_links_are_removed_with_their_item_list_and_owner(admin, alice, bob, db):
    lst = make_list(alice)
    keep = make_list(bob)
    make_item(bob, keep["id"], links=[link("https://bobs.example")])

    gone = make_item(alice, lst["id"], links=[link("https://a.example"), link("https://b.example")])
    assert _link_count(db) == 3
    assert alice.delete(f"/api/items/{gone['id']}").status_code == 200
    assert _link_count(db) == 1

    make_item(alice, lst["id"], links=[link("https://c.example")])
    assert alice.delete(f"/api/lists/{lst['id']}?force=true").status_code == 200
    assert [l.url for l in db.query(models.ItemLink)] == ["https://bobs.example"]

    # An administrator erasing a removed person's data takes their links too.
    mine = make_list(alice, "Another")
    make_item(alice, mine["id"], links=[link("https://d.example")])
    alice.post("/api/link-labels", {"name": "Menu"})
    alice_id = db.query(models.User).filter(models.User.email == alice.email).one().id
    assert admin.post(f"/api/admin/users/{alice_id}/revoke").status_code == 200
    assert admin.delete(f"/api/admin/users/{alice_id}").status_code == 200
    db.expire_all()
    assert [l.url for l in db.query(models.ItemLink)] == ["https://bobs.example"]
    assert db.query(models.LinkLabel).count() == 0


# --- each person's list of link labels ----------------------------------------------


def test_link_labels_are_private_and_names_are_unique_per_person(alice, bob):
    a = alice.post("/api/link-labels", {"name": "Menu"})
    assert a.status_code == 200
    assert alice.post("/api/link-labels", {"name": "menu"}).status_code == 409
    assert bob.post("/api/link-labels", {"name": "Menu"}).status_code == 200  # same name, different person

    lid = a.json()["id"]
    assert [l["name"] for l in bob.get("/api/link-labels").json()] == ["Menu"]
    assert bob.get("/api/link-labels").json()[0]["id"] != lid
    assert bob.patch(f"/api/link-labels/{lid}", {"name": "Hacked"}).status_code == 404
    assert bob.delete(f"/api/link-labels/{lid}").status_code == 404
    assert alice.get("/api/link-labels").json()[0]["name"] == "Menu"


def test_link_labels_can_be_renamed_reordered_and_deleted(alice):
    ids = [alice.post("/api/link-labels", {"name": n}).json()["id"] for n in ("Menu", "Reviews", "Map")]
    assert [l["name"] for l in alice.get("/api/link-labels").json()] == ["Menu", "Reviews", "Map"]

    assert alice.patch(f"/api/link-labels/{ids[1]}", {"name": "  Yelp  "}).json()["name"] == "Yelp"
    assert alice.patch(f"/api/link-labels/{ids[1]}", {"name": "map"}).status_code == 409
    assert alice.patch(f"/api/link-labels/{ids[1]}", {"name": "YELP"}).status_code == 200  # a label may change its own case
    assert alice.patch("/api/link-labels/9999", {"name": "x"}).status_code == 404

    order = alice.post("/api/link-labels/reorder", {"ordered_ids": [ids[2], ids[0], ids[1]]}).json()
    assert [l["name"] for l in order] == ["Map", "Menu", "YELP"]

    assert alice.delete(f"/api/link-labels/{ids[0]}").status_code == 200
    assert alice.delete(f"/api/link-labels/{ids[0]}").status_code == 404
    assert [l["name"] for l in alice.get("/api/link-labels").json()] == ["Map", "YELP"]


def test_link_label_names_are_checked(alice):
    for bad in ("", "x" * 41):
        assert alice.post("/api/link-labels", {"name": bad}).status_code == 422
    assert alice.post("/api/link-labels", {"name": "x" * 40}).status_code == 200


def test_reordering_ignores_someone_elses_labels(alice, bob):
    mine = alice.post("/api/link-labels", {"name": "Menu"}).json()["id"]
    theirs = bob.post("/api/link-labels", {"name": "Map"}).json()["id"]
    resp = alice.post("/api/link-labels/reorder", {"ordered_ids": [theirs, mine]})
    assert resp.status_code == 200 and [l["name"] for l in resp.json()] == ["Menu"]
    assert [l["name"] for l in bob.get("/api/link-labels").json()] == ["Map"]


def test_changing_or_deleting_a_label_leaves_links_that_used_it_alone(alice, bob):
    label = alice.post("/api/link-labels", {"name": "Menu"}).json()
    lst = make_list(alice)
    item = make_item(alice, lst["id"], links=[link("https://a.example", "Menu")])
    share(alice, lst["id"], bob, "view")

    alice.patch(f"/api/link-labels/{label['id']}", {"name": "Food menu"})
    assert bob.get(f"/api/items/{item['id']}").json()["links"][0]["label"] == "Menu"
    alice.delete(f"/api/link-labels/{label['id']}")
    assert bob.get(f"/api/items/{item['id']}").json()["links"][0]["label"] == "Menu"
    assert bob.get("/api/link-labels").json() == []  # and bob never saw alice's list at all


def test_the_link_labels_page_needs_an_account(alice, sign_in):
    assert alice.get("/link-labels.html").status_code == 200
    stranger = sign_in("nobody@example.com", enabled=False)
    assert stranger.get("/link-labels.html").status_code == 403
    assert stranger.get("/api/link-labels").status_code == 403


# --- the migration from a single url -------------------------------------------------


def test_existing_urls_become_each_items_first_link_and_come_back_on_downgrade(monkeypatch):
    """Run the migration over a database that still has `items.url` values."""
    old_head, new_head = "c4f1e8a29d63", "d8a2f5b61e37"
    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path.close()
    url = f"sqlite:///{path.name}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    engine = create_engine(url)
    try:
        command.upgrade(cfg, old_head)
        with engine.begin() as conn:
            conn.execute(text("insert into users (email) values ('o@example.com')"))
            conn.execute(text("insert into lists (name, owner_id) values ('L', 1)"))
            for i, address in enumerate(
                ["https://a.example/x", "  http://b.example  ", "c.example/page", "javascript:alert(1)", "mailto:me@example.com", "", None, "HTTPS://D.EXAMPLE"], start=1
            ):
                conn.execute(
                    text("insert into items (list_id, name, url, progress, sort_order, done, scrape_status) values (1, :n, :u, 0, :i, 0, 'not_started')"),
                    {"n": f"item {i}", "u": address, "i": i},
                )
        command.upgrade(cfg, new_head)
        with engine.connect() as conn:
            links = {row[0]: (row[1], row[2], row[3]) for row in conn.execute(text("select item_id, label, url, position from item_links"))}
            columns = [row[1] for row in conn.execute(text("pragma table_info(items)"))]
        assert "url" not in columns
        assert links == {
            1: (None, "https://a.example/x", 0),
            2: (None, "http://b.example", 0),  # spaces trimmed
            3: (None, "https://c.example/page", 0),  # no scheme: https assumed
            8: (None, "HTTPS://D.EXAMPLE", 0),
        }  # javascript:, mailto:, empty and null leave no link

        with engine.begin() as conn:
            conn.execute(text("insert into item_links (item_id, label, url, position) values (1, 'Menu', 'https://second.example', 1)"))
        command.downgrade(cfg, old_head)
        with engine.connect() as conn:
            urls = {row[0]: row[1] for row in conn.execute(text("select id, url from items"))}
        assert urls[1] == "https://a.example/x"  # the first link; the second is dropped
        assert urls[2] == "http://b.example" and urls[4] is None
    finally:
        engine.dispose()
        os.unlink(path.name)
        # The migrations' logging setup switches off the app's loggers (see conftest).
        for name in logging.root.manager.loggerDict:
            logging.getLogger(name).disabled = False
