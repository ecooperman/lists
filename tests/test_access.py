"""Who can see and do what. Every endpoint that takes a list, item, contact or
category id must treat someone else's as nonexistent (404), and a shared list
must give each role exactly its powers - these tests are the guard against a
missed filter leaking data between people."""
from app import models


def make_list(person, name="Gifts", **extra):
    resp = person.post("/api/lists", {"name": name, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_item(person, list_id, name="Socks", **extra):
    resp = person.post(f"/api/lists/{list_id}/items", {"name": name, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def share(owner, list_id, person, role):
    # Only people with an account can be added, and an account is made by
    # signing in - so they do that first.
    person.get("/api/me")
    resp = owner.post(f"/api/lists/{list_id}/members", {"email": person.email, "role": role})
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- strangers see nothing ---------------------------------------------------


def test_a_list_is_invisible_to_people_it_isnt_shared_with(alice, bob):
    lst = make_list(alice)
    item = make_item(alice, lst["id"])
    lid, iid = lst["id"], item["id"]

    assert bob.get("/api/lists").json() == []
    probes = [
        bob.get(f"/api/lists/{lid}"),
        bob.get(f"/api/lists/{lid}/items"),
        bob.get(f"/api/lists/{lid}/contacts"),
        bob.get(f"/api/lists/{lid}/members"),
        bob.post(f"/api/lists/{lid}/items", {"name": "x"}),
        bob.put(f"/api/lists/{lid}/items/order", {"item_ids": [iid]}),
        bob.post(f"/api/lists/{lid}/items/import", {"text": "- x"}),
        bob.post(f"/api/lists/{lid}/items/import/preview", {"text": "- x"}),
        bob.post(f"/api/lists/{lid}/members", {"email": "x@example.com", "role": "view"}),
        bob.patch(f"/api/lists/{lid}", {"name": "mine now"}),
        bob.delete(f"/api/lists/{lid}"),
        bob.get(f"/api/items/{iid}"),
        bob.patch(f"/api/items/{iid}", {"name": "mine now"}),
        bob.delete(f"/api/items/{iid}"),
        bob.post(f"/api/items/{iid}/scrape"),
    ]
    assert [r.status_code for r in probes] == [404] * len(probes)
    assert alice.get(f"/api/lists/{lid}").json()["name"] == "Gifts"
    assert alice.get(f"/api/items/{iid}").json()["name"] == "Socks"


def test_reordering_only_accepts_your_own_lists(alice, bob):
    mine, theirs = make_list(bob, "Mine"), make_list(alice, "Theirs")
    assert bob.put("/api/lists/order", {"list_ids": [mine["id"], theirs["id"]]}).status_code == 400


def test_moving_an_item_into_someone_elses_list_is_refused(alice, bob):
    theirs = make_list(alice, "Theirs")
    mine = make_list(bob, "Mine")
    item = make_item(bob, mine["id"])
    assert bob.patch(f"/api/items/{item['id']}", {"list_id": theirs["id"]}).status_code == 404


# --- roles ------------------------------------------------------------------


def test_view_role_can_read_but_not_change_anything(alice, bob):
    lst = make_list(alice)
    item = make_item(alice, lst["id"])
    share(alice, lst["id"], bob, "view")
    lid, iid = lst["id"], item["id"]

    seen = bob.get(f"/api/lists/{lid}").json()
    assert seen["my_role"] == "view" and seen["owner_email"] == alice.email
    assert [i["name"] for i in bob.get(f"/api/lists/{lid}/items").json()] == ["Socks"]

    refused = [
        bob.post(f"/api/lists/{lid}/items", {"name": "x"}),
        bob.patch(f"/api/items/{iid}", {"done": True}),
        bob.delete(f"/api/items/{iid}"),
        bob.put(f"/api/lists/{lid}/items/order", {"item_ids": [iid]}),
        bob.post(f"/api/lists/{lid}/items/import", {"text": "- x"}),
        bob.post(f"/api/items/{iid}/scrape"),
        bob.patch(f"/api/lists/{lid}", {"name": "x"}),
        bob.patch(f"/api/lists/{lid}", {"sort_mode": "priority"}),
        bob.delete(f"/api/lists/{lid}"),
        bob.get(f"/api/lists/{lid}/members"),
        bob.post(f"/api/lists/{lid}/members", {"email": "x@example.com", "role": "view"}),
    ]
    assert [r.status_code for r in refused] == [403] * len(refused)
    assert alice.get(f"/api/items/{iid}").json()["done"] is False


def test_edit_role_works_with_items_but_not_the_list_itself(alice, bob):
    lst = make_list(alice)
    share(alice, lst["id"], bob, "edit")
    lid = lst["id"]

    item = make_item(bob, lid, "Added by Bob")
    assert bob.patch(f"/api/items/{item['id']}", {"done": True}).json()["done"] is True
    assert bob.patch(f"/api/lists/{lid}", {"sort_mode": "priority"}).status_code == 200
    assert bob.post(f"/api/lists/{lid}/items/import", {"text": "- a\n- b"}).status_code == 200
    assert bob.delete(f"/api/items/{item['id']}").status_code == 200

    refused = [
        bob.patch(f"/api/lists/{lid}", {"name": "x"}),
        bob.patch(f"/api/lists/{lid}", {"purpose": "x"}),
        bob.patch(f"/api/lists/{lid}", {"locked": True}),
        bob.patch(f"/api/lists/{lid}", {"priority_labels": ["a", "b", "c", "d", "e"]}),
        bob.delete(f"/api/lists/{lid}"),
        bob.get(f"/api/lists/{lid}/members"),
        bob.post(f"/api/lists/{lid}/members", {"email": "x@example.com", "role": "view"}),
        bob.patch(f"/api/lists/{lid}/members/1", {"role": "view"}),
    ]
    assert [r.status_code for r in refused] == [403] * len(refused)


def test_only_the_owner_manages_sharing_and_can_delete(alice, bob, carol):
    lst = make_list(alice)
    lid = lst["id"]
    added = share(alice, lid, bob, "view")
    assert added["email"] == bob.email and added["role"] == "view"

    members = alice.get(f"/api/lists/{lid}/members").json()
    assert [(m["email"], m["role"]) for m in members] == [(alice.email, "owner"), (bob.email, "view")]

    assert alice.patch(f"/api/lists/{lid}/members/{added['user_id']}", {"role": "edit"}).json()["role"] == "edit"
    assert alice.post(f"/api/lists/{lid}/members", {"email": bob.email, "role": "view"}).status_code == 409
    assert alice.post(f"/api/lists/{lid}/members", {"email": "not-an-email", "role": "view"}).status_code == 400

    owner_row = members[0]
    assert alice.patch(f"/api/lists/{lid}/members/{owner_row['user_id']}", {"role": "view"}).status_code == 400
    assert alice.delete(f"/api/lists/{lid}/members/{owner_row['user_id']}").status_code == 400

    assert alice.delete(f"/api/lists/{lid}/members/{added['user_id']}").status_code == 200
    assert bob.get(f"/api/lists/{lid}").status_code == 404


def test_a_member_can_leave_but_not_remove_others(alice, bob, carol):
    lst = make_list(alice)
    lid = lst["id"]
    b = share(alice, lid, bob, "edit")
    c = share(alice, lid, carol, "view")

    assert bob.delete(f"/api/lists/{lid}/members/{c['user_id']}").status_code == 403
    assert bob.delete(f"/api/lists/{lid}/members/{b['user_id']}").status_code == 200
    assert bob.get(f"/api/lists/{lid}").status_code == 404
    assert carol.get(f"/api/lists/{lid}").status_code == 200


def test_deleting_a_list_removes_it_for_everyone(alice, bob):
    lst = make_list(alice)
    make_item(alice, lst["id"])
    share(alice, lst["id"], bob, "edit")
    resp = alice.delete(f"/api/lists/{lst['id']}?force=true")
    assert resp.status_code == 200 and resp.json()["deleted_items"] == 1
    assert bob.get("/api/lists").json() == []


def test_someone_who_has_never_signed_in_cant_be_added(alice, carol, db):
    lst = make_list(alice)
    resp = alice.post(f"/api/lists/{lst['id']}/members", {"email": carol.email, "role": "view"})
    assert resp.status_code == 404
    # Refusing leaves no account behind, so she isn't quietly given the list later.
    assert db.query(models.User).filter_by(email=carol.email).first() is None
    assert carol.get("/api/lists").json() == []


def test_the_pre_accounts_placeholder_cant_be_added(alice):
    lst = make_list(alice)
    resp = alice.post(f"/api/lists/{lst['id']}/members", {"email": "legacy-owner@lists.invalid", "role": "view"})
    assert resp.status_code == 400
    assert alice.post(f"/api/lists/{lst['id']}/invites", {"email": "legacy-owner@lists.invalid", "role": "view"}).status_code == 400


def test_emails_are_case_insensitive(alice, client):
    from tests.conftest import Person

    dana = Person(client, "DANA@example.com")
    dana.get("/api/me")
    lst = make_list(alice)
    assert alice.post(f"/api/lists/{lst['id']}/members", {"email": "  dana@Example.COM ", "role": "view"}).status_code == 200
    assert [l["name"] for l in dana.get("/api/lists").json()] == ["Gifts"]


# --- per-person arrangement ---------------------------------------------------


def test_each_person_orders_and_files_a_shared_list_themselves(alice, bob):
    first, second = make_list(alice, "First"), make_list(alice, "Second")
    share(alice, first["id"], bob, "view")
    share(alice, second["id"], bob, "view")

    bob_cat = bob.post("/api/categories", {"name": "Reading", "color": "#336699"}).json()
    assert bob.patch(f"/api/lists/{first['id']}", {"category_id": bob_cat["id"]}).status_code == 200  # even as a viewer
    assert bob.put("/api/lists/order", {"list_ids": [second["id"], first["id"]]}).status_code == 200

    assert [l["name"] for l in bob.get("/api/lists").json()] == ["Second", "First"]
    assert [l["name"] for l in alice.get("/api/lists").json()] == ["First", "Second"]
    assert {l["name"]: l["category_id"] for l in bob.get("/api/lists").json()} == {"Second": None, "First": bob_cat["id"]}
    assert {l["category_id"] for l in alice.get("/api/lists").json()} == {None}


def test_categories_are_private_and_names_are_unique_per_person(alice, bob):
    a = alice.post("/api/categories", {"name": "Work", "color": "#112233"})
    assert a.status_code == 200
    assert alice.post("/api/categories", {"name": "work", "color": "#112233"}).status_code == 409
    assert bob.post("/api/categories", {"name": "Work", "color": "#445566"}).status_code == 200  # same name, different person

    cid = a.json()["id"]
    assert [c["name"] for c in bob.get("/api/categories").json()] == ["Work"]
    assert bob.get("/api/categories").json()[0]["id"] != cid
    assert bob.patch(f"/api/categories/{cid}", {"color": "#000000"}).status_code == 404
    assert bob.delete(f"/api/categories/{cid}").status_code == 404

    bobs_list = make_list(bob)
    assert bob.patch(f"/api/lists/{bobs_list['id']}", {"category_id": cid}).status_code == 404  # can't file under hers


def test_a_category_in_use_by_a_shared_list_cant_be_deleted(alice):
    cat = alice.post("/api/categories", {"name": "Work", "color": "#112233"}).json()
    lst = make_list(alice)
    alice.patch(f"/api/lists/{lst['id']}", {"category_id": cat["id"]})
    assert alice.delete(f"/api/categories/{cat['id']}").status_code == 409


# --- contacts: a shared list uses its owner's address book ----------------------


def test_contacts_are_private_to_their_owner(alice, bob):
    c = alice.post("/api/contacts", {"first_name": "Zed", "email": "zed@example.com", "address": "1 Main St"}).json()
    assert bob.get("/api/contacts").json() == []
    assert bob.patch(f"/api/contacts/{c['id']}", {"first_name": "Hacked"}).status_code == 404
    assert bob.delete(f"/api/contacts/{c['id']}").status_code == 404


def test_shared_lists_offer_the_owners_contacts_as_names_only(alice, bob):
    zed = alice.post("/api/contacts", {"first_name": "Zed", "last_name": "Ng", "email": "zed@example.com", "address": "1 Main St"}).json()
    bobs_own = bob.post("/api/contacts", {"first_name": "Bobs"}).json()
    lst = make_list(alice)
    share(alice, lst["id"], bob, "edit")
    lid = lst["id"]

    offered = bob.get(f"/api/lists/{lid}/contacts").json()
    assert offered == [{"id": zed["id"], "first_name": "Zed", "last_name": "Ng"}]  # no email or address

    item = make_item(bob, lid, "Mug", recipient_id=zed["id"])
    assert item["recipient"] == {"id": zed["id"], "first_name": "Zed", "last_name": "Ng"}
    assert make_item(alice, lid, "Hat", recipient_id=zed["id"])["recipient"]["first_name"] == "Zed"
    for resp in (bob.get(f"/api/lists/{lid}/items"), alice.get(f"/api/items/{item['id']}")):
        assert "zed@example.com" not in resp.text and "1 Main St" not in resp.text

    # Bob's own contact isn't on Alice's list's address book.
    assert bob.post(f"/api/lists/{lid}/items", {"name": "x", "recipient_id": bobs_own["id"]}).status_code == 404
    assert bob.patch(f"/api/items/{item['id']}", {"recipient_id": bobs_own["id"]}).status_code == 404


def test_moving_an_item_between_address_books_clears_the_recipient(alice, bob):
    zed = alice.post("/api/contacts", {"first_name": "Zed"}).json()
    shared = make_list(alice, "Shared")
    share(alice, shared["id"], bob, "edit")
    mine = make_list(bob, "Mine")
    item = make_item(bob, shared["id"], "Mug", recipient_id=zed["id"])

    moved = bob.patch(f"/api/items/{item['id']}", {"list_id": mine["id"]})
    assert moved.status_code == 200
    assert moved.json()["list_id"] == mine["id"] and moved.json()["recipient"] is None


def test_moving_an_item_needs_edit_access_to_the_destination(alice, bob):
    readonly = make_list(alice, "Readonly")
    share(alice, readonly["id"], bob, "view")
    mine = make_list(bob, "Mine")
    item = make_item(bob, mine["id"])
    assert bob.patch(f"/api/items/{item['id']}", {"list_id": readonly["id"]}).status_code == 403


def test_a_contact_cant_be_deleted_while_a_shared_list_uses_it(alice, bob):
    zed = alice.post("/api/contacts", {"first_name": "Zed"}).json()
    lst = make_list(alice)
    share(alice, lst["id"], bob, "edit")
    make_item(bob, lst["id"], recipient_id=zed["id"])
    assert alice.delete(f"/api/contacts/{zed['id']}").status_code == 409


# --- accounts ------------------------------------------------------------------


def test_me_creates_the_user_on_first_sight(alice, db):
    assert db.query(models.User).filter_by(email=alice.email).first() is None
    assert alice.get("/api/me").json()["email"] == alice.email
    assert db.query(models.User).filter_by(email=alice.email).count() == 1


def test_the_first_admin_to_sign_in_takes_over_pre_accounts_data(client, db, bob):
    from app import config, crud
    from tests.conftest import Person

    legacy = db.query(models.User).filter_by(email=crud.LEGACY_OWNER_EMAIL).one()
    old_list = models.ItemList(name="Old list", owner_id=legacy.id)
    db.add(old_list)
    db.flush()
    db.add(models.ListMember(list_id=old_list.id, user_id=legacy.id, role="owner", sort_order=0))
    db.commit()

    # Someone who isn't an admin signing in first doesn't get it.
    assert bob.get("/api/lists").json() == []

    owner = Person(client, config.DEV_USER_EMAIL)
    assert [(l["name"], l["my_role"]) for l in owner.get("/api/lists").json()] == [("Old list", "owner")]
    assert owner.get("/api/me").json()["email"] == config.DEV_USER_EMAIL
    assert db.query(models.User).filter_by(email=crud.LEGACY_OWNER_EMAIL).first() is None


def test_adding_someone_already_on_the_list_says_so(alice, bob):
    lst = make_list(alice)
    share(alice, lst["id"], bob, "edit")

    # Typing your own address is the likeliest slip - and it isn't about Cloudflare at all.
    mine = alice.post(f"/api/lists/{lst['id']}/members", {"email": alice.email, "role": "view"})
    assert mine.status_code == 409
    assert "That's you" in mine.json()["detail"]

    again = alice.post(f"/api/lists/{lst['id']}/members", {"email": bob.email.upper(), "role": "view"})
    assert again.status_code == 409
    detail = again.json()["detail"]
    assert bob.email in detail and "already on this list" in detail and "can edit" in detail


def test_someone_on_the_list_is_reported_even_if_cloudflare_no_longer_lets_them_in(alice, bob, monkeypatch):
    from shared_python import cloudflare

    lst = make_list(alice)
    share(alice, lst["id"], bob, "view")
    monkeypatch.setattr(cloudflare, "is_let_in", lambda email, admin_emails=(): False)
    resp = alice.post(f"/api/lists/{lst['id']}/members", {"email": bob.email, "role": "edit"})
    # Not "can't sign in yet", which would offer to invite someone already here.
    assert resp.status_code == 409
    assert "already on this list" in resp.json()["detail"]
