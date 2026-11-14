from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from . import config, models, schemas

# Parked owner of everything that existed before accounts did (see the
# migration); the first person to sign in takes it over (user_for_request).
LEGACY_OWNER_EMAIL = "legacy-owner@lists.invalid"


# --- users ---


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def _create_user(db: Session, email: str) -> models.User:
    user = models.User(email=email)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two first requests from the same person raced; theirs won.
        db.rollback()
        return get_user_by_email(db, email)
    db.refresh(user)
    return user


def user_for_request(db: Session, email: str):
    """The account behind an (already normalized) email that has passed the
    login gate, as (user, None), or (None, problem) with problem "none" (never
    enabled in this app) or "removed". Nobody gets an account just by turning
    up: only an administrator's email does, plus - before anyone has set
    ADMIN_EMAILS in production - the first person in, who takes over the
    pre-accounts data by having the placeholder owner renamed to their email,
    so it all becomes theirs without moving a single row. Everyone else was
    given an account by an approved invite or the Users page."""
    user = get_user_by_email(db, email)
    is_admin_email = email in config.ADMIN_EMAILS
    if user is not None:
        if user.status == models.USER_REMOVED and not is_admin_email:
            return None, "removed"
        return user, None
    legacy = get_user_by_email(db, LEGACY_OWNER_EMAIL) if (config.ADOPT_LEGACY_ANY or is_admin_email) else None
    if legacy is not None:
        legacy.email = email
        db.commit()
        return legacy, None
    if is_admin_email:
        return _create_user(db, email), None
    return None, "none"


def get_users_overview(db: Session):
    """Everyone with an account (the pre-accounts placeholder aside) with what
    they own, for the administrator's Users page. Counted per person - there
    are a handful of people, not thousands."""
    overview = []
    users = db.query(models.User).filter(models.User.email != LEGACY_OWNER_EMAIL).order_by(models.User.email).all()
    for user in users:
        owned_ids = [i for (i,) in db.query(models.ItemList.id).filter(models.ItemList.owner_id == user.id)]
        on_lists = db.query(func.count(models.ListMember.list_id)).filter(models.ListMember.user_id == user.id).scalar()
        others = 0
        items = 0
        if owned_ids:
            others = (
                db.query(func.count(func.distinct(models.ListMember.user_id)))
                .filter(models.ListMember.list_id.in_(owned_ids), models.ListMember.user_id != user.id)
                .scalar()
            )
            items = db.query(func.count(models.Item.id)).filter(models.Item.list_id.in_(owned_ids)).scalar()
        overview.append(
            schemas.AdminUser(
                id=user.id,
                email=user.email,
                status=user.status,
                is_admin=user.email in config.ADMIN_EMAILS,
                created_at=user.created_at,
                owned_lists=len(owned_ids),
                shared_with_them=on_lists - len(owned_ids),
                people_on_their_lists=others,
                items=items,
                contacts=db.query(func.count(models.Contact.id)).filter(models.Contact.owner_id == user.id).scalar(),
                categories=db.query(func.count(models.Category.id)).filter(models.Category.owner_id == user.id).scalar(),
            )
        )
    return overview


def get_user(db: Session, user_id: int):
    """An account by id, or None (the pre-accounts placeholder isn't one)."""
    user = db.get(models.User, user_id)
    return None if user is None or user.email == LEGACY_OWNER_EMAIL else user


def set_user_status(db: Session, user: models.User, status: str) -> models.User:
    user.status = status
    db.commit()
    db.refresh(user)
    return user


def delete_user_data(db: Session, user: models.User) -> None:
    """Erase everything this person owns or made, keeping only their (removed)
    account row so that signing in again can't hand them a fresh one. Their
    lists go for everyone they were shared with, and the requests they made to
    have people let in go too (the people already let in keep their accounts).
    Their place on other people's lists goes; those lists are untouched."""
    for db_list in db.query(models.ItemList).filter(models.ItemList.owner_id == user.id).all():
        _delete_links_of_list_items(db, db_list.id)
        db.query(models.Item).filter(models.Item.list_id == db_list.id).delete()
        db.query(models.Invite).filter(
            models.Invite.list_id == db_list.id, models.Invite.status != models.INVITE_APPROVED
        ).delete()
        db.delete(db_list)  # its member rows go with it (cascade); approved requests keep a NULL list
    db.flush()
    db.query(models.ListMember).filter(models.ListMember.user_id == user.id).delete()
    db.query(models.Invite).filter(models.Invite.invited_by_id == user.id).delete()
    # Nothing outside their own lists can point at their address book or
    # categories, but make sure of it rather than leave a dangling reference.
    contact_ids = [i for (i,) in db.query(models.Contact.id).filter(models.Contact.owner_id == user.id)]
    if contact_ids:
        db.query(models.Item).filter(models.Item.recipient_id.in_(contact_ids)).update(
            {models.Item.recipient_id: None}, synchronize_session=False
        )
    category_ids = [i for (i,) in db.query(models.Category.id).filter(models.Category.owner_id == user.id)]
    if category_ids:
        db.query(models.ListMember).filter(models.ListMember.category_id.in_(category_ids)).update(
            {models.ListMember.category_id: None}, synchronize_session=False
        )
    db.query(models.Contact).filter(models.Contact.owner_id == user.id).delete()
    db.query(models.Category).filter(models.Category.owner_id == user.id).delete()
    db.query(models.LinkLabel).filter(models.LinkLabel.owner_id == user.id).delete()
    db.query(models.CopyEmail).filter(models.CopyEmail.user_id == user.id).delete()
    db.commit()


# --- contacts ---


def get_contacts(db: Session, owner_id: int):
    return (
        db.query(models.Contact)
        .filter(models.Contact.owner_id == owner_id)
        .order_by(models.Contact.first_name, models.Contact.last_name)
        .all()
    )


def get_contact(db: Session, owner_id: int, contact_id: int):
    return db.query(models.Contact).filter(models.Contact.owner_id == owner_id, models.Contact.id == contact_id).first()


def create_contact(db: Session, owner_id: int, contact: schemas.ContactCreate):
    db_contact = models.Contact(owner_id=owner_id, **contact.model_dump())
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def update_contact(db: Session, owner_id: int, contact_id: int, updates: schemas.ContactUpdate):
    db_contact = get_contact(db, owner_id, contact_id)
    if db_contact is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_contact, field, value)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def delete_contact(db: Session, owner_id: int, contact_id: int) -> str:
    db_contact = get_contact(db, owner_id, contact_id)
    if db_contact is None:
        return "not_found"
    still_in_use = db.query(models.Item).filter(models.Item.recipient_id == contact_id).first()
    if still_in_use is not None:
        return "in_use"
    db.delete(db_contact)
    db.commit()
    return "ok"


def contact_usable_for_list(db: Session, contact_id: int, list_id: int) -> bool:
    """A recipient has to come from the address book of the list's owner -
    that's whose contacts a shared list offers everyone."""
    return (
        db.query(models.Contact.id)
        .join(models.ItemList, models.ItemList.owner_id == models.Contact.owner_id)
        .filter(models.Contact.id == contact_id, models.ItemList.id == list_id)
        .first()
        is not None
    )


def get_list_contacts(db: Session, list_id: int):
    """The contacts a list's items can be addressed to: its owner's."""
    return (
        db.query(models.Contact)
        .join(models.ItemList, models.ItemList.owner_id == models.Contact.owner_id)
        .filter(models.ItemList.id == list_id)
        .order_by(models.Contact.first_name, models.Contact.last_name)
        .all()
    )


def _delete_links_of_list_items(db: Session, list_id: int) -> None:
    """Items are removed in bulk (no ORM cascade), so their links go first."""
    item_ids = db.query(models.Item.id).filter(models.Item.list_id == list_id)
    db.query(models.ItemLink).filter(models.ItemLink.item_id.in_(item_ids)).delete(synchronize_session=False)


# --- link labels ---
#
# A person's own list of labels for the links on items (see models.LinkLabel);
# the same shape as categories, minus the colors.


def get_link_labels(db: Session, owner_id: int):
    return (
        db.query(models.LinkLabel)
        .filter(models.LinkLabel.owner_id == owner_id)
        .order_by(models.LinkLabel.sort_order, models.LinkLabel.id)
        .all()
    )


def get_link_label(db: Session, owner_id: int, label_id: int):
    return (
        db.query(models.LinkLabel)
        .filter(models.LinkLabel.owner_id == owner_id, models.LinkLabel.id == label_id)
        .first()
    )


def link_label_name_taken(db: Session, owner_id: int, name: str, exclude_id: Optional[int] = None) -> bool:
    query = db.query(models.LinkLabel).filter(
        models.LinkLabel.owner_id == owner_id, func.lower(models.LinkLabel.name) == name.strip().lower()
    )
    if exclude_id is not None:
        query = query.filter(models.LinkLabel.id != exclude_id)
    return query.first() is not None


def create_link_label(db: Session, owner_id: int, label: schemas.LinkLabelCreate):
    top = db.query(func.max(models.LinkLabel.sort_order)).filter(models.LinkLabel.owner_id == owner_id).scalar() or 0
    db_label = models.LinkLabel(owner_id=owner_id, name=label.name.strip(), sort_order=top + 10)
    db.add(db_label)
    db.commit()
    db.refresh(db_label)
    return db_label


def update_link_label(db: Session, owner_id: int, label_id: int, updates: schemas.LinkLabelUpdate):
    db_label = get_link_label(db, owner_id, label_id)
    if db_label is None:
        return None
    if updates.name is not None:
        db_label.name = updates.name.strip()
    db.commit()
    db.refresh(db_label)
    return db_label


def reorder_link_labels(db: Session, owner_id: int, ordered_ids):
    by_id = {
        label.id: label
        for label in db.query(models.LinkLabel).filter(models.LinkLabel.owner_id == owner_id, models.LinkLabel.id.in_(ordered_ids))
    }
    for index, label_id in enumerate(ordered_ids):
        if label_id in by_id:  # a stale (or someone else's) id is skipped, not an error
            by_id[label_id].sort_order = (index + 1) * 10
    db.commit()
    return get_link_labels(db, owner_id)


def delete_link_label(db: Session, owner_id: int, label_id: int) -> bool:
    """Always allowed when it exists: links carry their own copy of the text,
    so deleting a label from your list leaves every link as it was."""
    db_label = get_link_label(db, owner_id, label_id)
    if db_label is None:
        return False
    db.delete(db_label)
    db.commit()
    return True


# --- categories ---


def get_categories(db: Session, owner_id: int):
    return (
        db.query(models.Category)
        .filter(models.Category.owner_id == owner_id)
        .order_by(models.Category.sort_order, models.Category.id)
        .all()
    )


def get_category(db: Session, owner_id: int, category_id: int):
    return (
        db.query(models.Category)
        .filter(models.Category.owner_id == owner_id, models.Category.id == category_id)
        .first()
    )


def category_name_taken(db: Session, owner_id: int, name: str, exclude_id: Optional[int] = None) -> bool:
    query = db.query(models.Category).filter(
        models.Category.owner_id == owner_id, func.lower(models.Category.name) == name.strip().lower()
    )
    if exclude_id is not None:
        query = query.filter(models.Category.id != exclude_id)
    return query.first() is not None


def create_category(db: Session, owner_id: int, category: schemas.CategoryCreate):
    # Appended to the end with gaps (max+10), same as trip-planning's.
    top = (
        db.query(func.max(models.Category.sort_order)).filter(models.Category.owner_id == owner_id).scalar() or 0
    )
    data = category.model_dump()
    data["name"] = data["name"].strip()
    db_category = models.Category(owner_id=owner_id, **data, sort_order=top + 10)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def update_category(db: Session, owner_id: int, category_id: int, updates: schemas.CategoryUpdate):
    db_category = get_category(db, owner_id, category_id)
    if db_category is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_category, field, value.strip() if field == "name" and value else value)
    db.commit()
    db.refresh(db_category)
    return db_category


def reorder_categories(db: Session, owner_id: int, ordered_ids):
    by_id = {
        c.id: c
        for c in db.query(models.Category).filter(models.Category.owner_id == owner_id, models.Category.id.in_(ordered_ids))
    }
    for index, category_id in enumerate(ordered_ids):
        if category_id in by_id:  # a stale (or someone else's) id is skipped, not an error
            by_id[category_id].sort_order = (index + 1) * 10
    db.commit()
    return get_categories(db, owner_id)


def delete_category(db: Session, owner_id: int, category_id: int) -> str:
    db_category = get_category(db, owner_id, category_id)
    if db_category is None:
        return "not_found"
    # Same guard as contacts: never silently orphan lists.
    if db.query(models.ListMember).filter(models.ListMember.category_id == category_id).first() is not None:
        return "in_use"
    db.delete(db_category)
    db.commit()
    return "ok"


# --- lists ---
#
# A list is only ever reached through the caller's ListMember row (see
# get_membership), which is what makes it theirs to see: no row, no list.


def get_membership(db: Session, user_id: int, list_id: int):
    return (
        db.query(models.ListMember)
        .options(joinedload(models.ListMember.list).joinedload(models.ItemList.owner))
        .filter(models.ListMember.user_id == user_id, models.ListMember.list_id == list_id)
        .first()
    )


def list_views(db: Session, members):
    """The member rows' lists, each decorated for the person the row belongs
    to (see schemas.ItemList): their position and category, their role, who
    owns it, how many people share it, and the item counts."""
    list_ids = [m.list_id for m in members]
    counts = {
        list_id: (total, open_)
        for list_id, total, open_ in db.query(
            models.Item.list_id,
            func.count(models.Item.id),
            func.coalesce(func.sum(case((models.Item.done.is_(False), 1), else_=0)), 0),
        )
        .filter(models.Item.list_id.in_(list_ids))
        .group_by(models.Item.list_id)
    }
    # Cost totals for the lists that track them: each item counts at its final cost, or its
    # estimate if there is no final one yet; done items are "bought".
    cost = func.coalesce(models.Item.final_cents, models.Item.estimate_cents)
    costs = {
        list_id: (int(total), int(bought), int(unpriced))
        for list_id, total, bought, unpriced in db.query(
            models.Item.list_id,
            func.coalesce(func.sum(cost), 0),
            func.coalesce(func.sum(case((models.Item.done.is_(True), cost), else_=0)), 0),
            func.coalesce(func.sum(case((cost.is_(None), 1), else_=0)), 0),
        )
        .filter(models.Item.list_id.in_(list_ids))
        .group_by(models.Item.list_id)
    }
    # The same total split by priority level (None = items with no priority), only for the
    # lists that track costs; levels that add up to nothing are left out.
    by_priority = {}
    tracked = [m.list_id for m in members if m.list.track_costs]
    if tracked:
        for list_id, priority, total in (
            db.query(models.Item.list_id, models.Item.priority, func.coalesce(func.sum(cost), 0))
            .filter(models.Item.list_id.in_(tracked))
            .group_by(models.Item.list_id, models.Item.priority)
        ):
            if total:
                by_priority.setdefault(list_id, []).append({"priority": priority, "total_cents": int(total)})
    # Highest level first, no-priority last, so the breakdown reads most important to least.
    for buckets in by_priority.values():
        buckets.sort(key=lambda b: -(b["priority"] or 0))
    member_counts = dict(
        db.query(models.ListMember.list_id, func.count(models.ListMember.user_id))
        .filter(models.ListMember.list_id.in_(list_ids))
        .group_by(models.ListMember.list_id)
        .all()
    )
    views = []
    for member in members:
        item_list = member.list
        item_list.sort_order = member.sort_order
        item_list.category_id = member.category_id
        item_list.my_role = member.role
        item_list.owner_email = item_list.owner.email
        item_list.member_count = member_counts.get(member.list_id, 1)
        item_list.item_count, item_list.open_count = counts.get(member.list_id, (0, 0))
        item_list.cost_total_cents, item_list.cost_bought_cents, item_list.unpriced_count = (
            costs.get(member.list_id, (0, 0, 0)) if item_list.track_costs else (0, 0, 0)
        )
        item_list.cost_by_priority = by_priority.get(member.list_id, []) if item_list.track_costs else []
        views.append(item_list)
    return views


def get_lists(db: Session, user_id: int):
    members = (
        db.query(models.ListMember)
        .options(joinedload(models.ListMember.list).joinedload(models.ItemList.owner))
        .filter(models.ListMember.user_id == user_id)
        .order_by(models.ListMember.sort_order, models.ListMember.list_id)
        .all()
    )
    return list_views(db, members)


def list_view(db: Session, member: models.ListMember):
    return list_views(db, [member])[0]


def _next_list_order(db: Session, user_id: int) -> int:
    top = db.query(func.max(models.ListMember.sort_order)).filter(models.ListMember.user_id == user_id).scalar()
    return 0 if top is None else top + 1


def reorder_lists(db: Session, user_id: int, list_ids) -> bool:
    """Give the listed lists positions 0..n-1 on this person's index, in the
    order given. False (and nothing changed) if an id repeats or isn't a list
    they're a member of."""
    if len(set(list_ids)) != len(list_ids):
        return False
    rows = {
        row.list_id: row
        for row in db.query(models.ListMember).filter(
            models.ListMember.user_id == user_id, models.ListMember.list_id.in_(list_ids)
        )
    }
    if len(rows) != len(list_ids):
        return False
    for position, list_id in enumerate(list_ids):
        rows[list_id].sort_order = position
    db.commit()
    return True


def create_list(db: Session, user: models.User, item_list: schemas.ItemListCreate):
    db_list = models.ItemList(owner_id=user.id, **item_list.model_dump())
    db.add(db_list)
    db.flush()
    db.add(
        models.ListMember(
            list_id=db_list.id, user_id=user.id, role=models.ROLE_OWNER, sort_order=_next_list_order(db, user.id)
        )
    )
    db.commit()
    return list_view(db, get_membership(db, user.id, db_list.id))


def update_list(db: Session, member: models.ListMember, list_fields: dict, member_fields: dict):
    """list_fields are the list's own (everyone sees them change);
    member_fields are this person's alone (their category)."""
    for field, value in list_fields.items():
        setattr(member.list, field, value)
    if not member.list.track_costs and member.list.sort_mode == "price":
        member.list.sort_mode = "manual"  # there are no prices to sort by any more
    for field, value in member_fields.items():
        setattr(member, field, value)
    db.commit()
    return list_view(db, get_membership(db, member.user_id, member.list_id))


def delete_list(db: Session, member: models.ListMember, force: bool = False):
    """Returns (result, deleted_item_count). A locked list is always refused
    ("locked"), force or not - unlock it first. A non-empty list is refused
    ("in_use", same guard as delete_contact) unless force=True, which deletes
    its items along with it - callers should only pass that after the user
    has been told how many items are about to go. Deleting removes the list
    for everyone it's shared with."""
    db_list = member.list
    if db_list.locked:
        return "locked", 0
    item_count = db.query(func.count(models.Item.id)).filter(models.Item.list_id == db_list.id).scalar()
    if item_count and not force:
        return "in_use", 0
    _delete_links_of_list_items(db, db_list.id)
    deleted = db.query(models.Item).filter(models.Item.list_id == db_list.id).delete()
    # Unfinished invite requests go with the list; approved ones stay (the
    # ORM nulls their list_id) because the person was let in and still counts
    # against what their inviter may ask for.
    db.query(models.Invite).filter(
        models.Invite.list_id == db_list.id, models.Invite.status != models.INVITE_APPROVED
    ).delete()
    db.delete(db_list)  # its member rows go with it (cascade)
    db.commit()
    return "ok", deleted


# --- who has access ---


def get_members(db: Session, list_id: int):
    return (
        db.query(models.ListMember)
        .options(joinedload(models.ListMember.user))
        .filter(models.ListMember.list_id == list_id)
        .order_by((models.ListMember.role == models.ROLE_OWNER).desc(), models.ListMember.user_id)
        .all()
    )


def get_account(db: Session, email: str):
    """The person with this (already normalized) email if the app has an
    account for them, active or removed. Not the same as being able to sign in
    now - see signin.py's can_sign_in, which also looks at the status and asks
    Cloudflare."""
    if email == LEGACY_OWNER_EMAIL:
        return None
    return get_user_by_email(db, email)


def enable_user(db: Session, email: str) -> models.User:
    """Make sure this email has an active account here: create one, or switch a
    removed person back on. Only for an administrator's decision (approving an
    invite, adding or restoring someone on the Users page)."""
    user = get_account(db, email) or _create_user(db, email)
    if user.status != models.USER_ACTIVE:
        user.status = models.USER_ACTIVE
        db.commit()
    return user


def add_member(db: Session, list_id: int, user: models.User, role: str):
    """Give an existing user access to a list. Returns the new membership, or
    None if they're already on it."""
    if db.query(models.ListMember).filter_by(list_id=list_id, user_id=user.id).first() is not None:
        return None
    member = models.ListMember(list_id=list_id, user_id=user.id, role=role, sort_order=_next_list_order(db, user.id))
    member.category_id = _category_for_new_member(db, list_id, user.id)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _category_for_new_member(db: Session, list_id: int, user_id: int):
    """Which of the new member's own categories to file a freshly shared list
    under: the one its owner filed it in, copied over (name and colours) if
    they have no category of that name yet, else their own same-named one
    (their colour kept). A one-time copy: nothing is linked afterwards, so
    changing or deleting it never touches the owner's. None if the owner
    hasn't filed the list."""
    owner = (
        db.query(models.ListMember)
        .join(models.ItemList, models.ItemList.id == models.ListMember.list_id)
        .filter(models.ListMember.list_id == list_id, models.ListMember.user_id == models.ItemList.owner_id)
        .first()
    )
    if owner is None or owner.category is None:
        return None
    theirs = (
        db.query(models.Category)
        .filter(models.Category.owner_id == user_id, func.lower(models.Category.name) == owner.category.name.strip().lower())
        .first()
    )
    if theirs is None:
        top = db.query(func.max(models.Category.sort_order)).filter(models.Category.owner_id == user_id).scalar() or 0
        theirs = models.Category(
            owner_id=user_id,
            name=owner.category.name,
            color=owner.category.color,
            text_color=owner.category.text_color,
            sort_order=top + 10,
        )
        db.add(theirs)
        db.flush()
    return theirs.id


def get_member(db: Session, list_id: int, user_id: int):
    return (
        db.query(models.ListMember)
        .options(joinedload(models.ListMember.user))
        .filter_by(list_id=list_id, user_id=user_id)
        .first()
    )


def set_member_role(db: Session, member: models.ListMember, role: str):
    member.role = role
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, member: models.ListMember):
    db.delete(member)
    db.commit()


# --- invites ---
#
# Asking for someone with no account to be let in. A list's owner asks, an
# administrator decides (see app/routers/invites.py for the Cloudflare step).


def _is_admin_email(user: models.User) -> bool:
    return user.email in config.ADMIN_EMAILS


def invites_left(db: Session, user: models.User):
    """How many more people this person may ask for, or None for no limit
    (administrators). Each different email they've asked for counts once, in
    any state - waiting, approved, declined - until they cancel a waiting one,
    so being refused doesn't hand the slot back to be spent again."""
    if _is_admin_email(user):
        return None
    used = (
        db.query(func.count(func.distinct(models.Invite.email))).filter(models.Invite.invited_by_id == user.id).scalar()
    )
    return max(config.INVITES_PER_USER - used, 0)


def copy_emails_left(db: Session, user: models.User) -> Optional[int]:
    """How many more copies this person may email today (a rolling 24 hours);
    None for an administrator, who has no limit."""
    if _is_admin_email(user):
        return None
    since = datetime.utcnow() - timedelta(days=1)
    used = db.query(func.count(models.CopyEmail.id)).filter(
        models.CopyEmail.user_id == user.id, models.CopyEmail.sent_at > since
    ).scalar()
    return max(config.COPY_EMAILS_PER_DAY - used, 0)


def record_copy_email(db: Session, user: models.User) -> None:
    db.add(models.CopyEmail(user_id=user.id))
    db.commit()


def create_invite(db: Session, list_id: Optional[int], inviter: models.User, email: str, role: str, for_app: bool = False):
    """Returns (invite, None), or (None, reason) with reason "duplicate" (this
    person was already asked for on this list, or for the app) or "none_left".
    An invite to the app itself (for_app) has no list."""
    if for_app:
        already = db.query(models.Invite).filter_by(for_app=True, email=email).first()
    else:
        already = db.query(models.Invite).filter_by(list_id=list_id, email=email).first()
    if already is not None:
        return None, "duplicate"
    left = invites_left(db, inviter)
    asked_before = db.query(models.Invite).filter_by(invited_by_id=inviter.id, email=email).first() is not None
    if left is not None and left <= 0 and not asked_before:
        return None, "none_left"
    invite = models.Invite(list_id=list_id, email=email, role=role, invited_by_id=inviter.id, for_app=for_app)
    db.add(invite)
    try:
        db.commit()
    except IntegrityError:  # the same request raced in twice
        db.rollback()
        return None, "duplicate"
    db.refresh(invite)
    return invite, None


def get_app_invite(db: Session, email: str):
    """The request already made to let this email into the app itself, in any state."""
    return db.query(models.Invite).filter_by(for_app=True, email=email).first()


def get_declined_invites(db: Session):
    """Every declined request (to the app or to a list), newest decision first, for the
    administrator to review and, if they like, allow again."""
    invites = (
        db.query(models.Invite)
        .options(joinedload(models.Invite.list), joinedload(models.Invite.invited_by))
        .filter(models.Invite.status == models.INVITE_DECLINED)
        .order_by(models.Invite.decided_at.desc(), models.Invite.id.desc())
        .all()
    )
    for invite in invites:
        invite.invited_by_email = invite.invited_by.email
        invite.list_name = invite.list.name if invite.list is not None else None
    return invites


def get_my_app_invites(db: Session, user: models.User):
    """The requests this person made to let people into the app itself, any state."""
    return db.query(models.Invite).filter_by(for_app=True, invited_by_id=user.id).order_by(models.Invite.id).all()


def get_list_invite(db: Session, list_id: int, email: str):
    """The request already made for this email on this list, in any state."""
    return db.query(models.Invite).filter_by(list_id=list_id, email=email).first()


def get_invite(db: Session, invite_id: int):
    return (
        db.query(models.Invite)
        .options(joinedload(models.Invite.list), joinedload(models.Invite.invited_by))
        .filter(models.Invite.id == invite_id)
        .first()
    )


def get_list_invites(db: Session, list_id: int):
    """Requests on this list still to be (or already) answered - approved ones
    are people on the list by now, so they show up as members instead."""
    return (
        db.query(models.Invite)
        .filter(models.Invite.list_id == list_id, models.Invite.status != models.INVITE_APPROVED)
        .order_by(models.Invite.id)
        .all()
    )


def known_people(db: Session, user: models.User):
    """Emails to suggest when this person is sharing something: everyone on a
    list they own (other than themselves) and everyone they have asked to be
    let in (except those refused), lowercased and sorted. Only people they have
    already dealt with - never everyone who has an account here."""
    owned = (
        db.query(models.ListMember.list_id)
        .filter(models.ListMember.user_id == user.id, models.ListMember.role == models.ROLE_OWNER)
        .subquery()
    )
    shared_with = (
        db.query(models.User.email)
        .join(models.ListMember, models.ListMember.user_id == models.User.id)
        .filter(models.ListMember.list_id.in_(db.query(owned.c.list_id)), models.User.id != user.id)
    )
    asked = db.query(models.Invite.email).filter(
        models.Invite.invited_by_id == user.id, models.Invite.status != models.INVITE_DECLINED
    )
    return sorted({email.lower() for (email,) in shared_with.union(asked).all()} - {user.email.lower()})


def pending_invite_count(db: Session) -> int:
    return db.query(func.count(models.Invite.id)).filter(models.Invite.status == models.INVITE_PENDING).scalar()


def get_pending_invites(db: Session):
    invites = (
        db.query(models.Invite)
        .options(joinedload(models.Invite.list), joinedload(models.Invite.invited_by))
        .filter(models.Invite.status == models.INVITE_PENDING)
        .order_by(models.Invite.id)
        .all()
    )
    for invite in invites:
        invite.invited_by_email = invite.invited_by.email
        invite.list_name = invite.list.name if invite.list is not None else None
    return invites


def cancel_invite(db: Session, invite: models.Invite) -> None:
    db.delete(invite)
    db.commit()


def grant_invite(db: Session, invite: models.Invite) -> models.Invite:
    """Record that the invited person was let in: they get an active account
    here and their place on the list."""
    user = enable_user(db, invite.email)
    if invite.list_id is not None:
        add_member(db, invite.list_id, user, invite.role)  # None if they're somehow on it already
    invite.status = models.INVITE_APPROVED
    invite.decided_at = datetime.utcnow()
    db.commit()
    return invite


def decline_invite(db: Session, invite: models.Invite) -> models.Invite:
    invite.status = models.INVITE_DECLINED
    invite.decided_at = datetime.utcnow()
    db.commit()
    return invite


# --- items ---
#
# Item functions take ids and assume the caller has already checked access to
# the list (see app/access.py) - they're only ever reached through it.


def get_items(db: Session, list_id: int):
    sort_mode = db.query(models.ItemList.sort_mode).filter(models.ItemList.id == list_id).scalar()
    # Done items always sink to the bottom. Within each group: the list's own
    # manual order, or - in priority mode - highest priority first with ties
    # kept in manual order (id only breaks exact sort_order ties).
    order = [models.Item.done]
    if sort_mode == "priority":
        order.append(models.Item.priority.desc().nulls_last())
    elif sort_mode == "price":
        order.append(func.coalesce(models.Item.final_cents, models.Item.estimate_cents).desc().nulls_last())
    order += [models.Item.sort_order, models.Item.id]
    return (
        db.query(models.Item)
        .options(joinedload(models.Item.recipient), selectinload(models.Item.links))
        .filter(models.Item.list_id == list_id)
        .order_by(*order)
        .all()
    )


def _next_sort_order(db: Session, list_id: int) -> int:
    top = db.query(func.max(models.Item.sort_order)).filter(models.Item.list_id == list_id).scalar()
    return 0 if top is None else top + 1


def get_item(db: Session, item_id: int):
    return (
        db.query(models.Item)
        .options(joinedload(models.Item.recipient), selectinload(models.Item.links))
        .filter(models.Item.id == item_id)
        .first()
    )


def _links_from(links) -> list:
    """ItemLink rows, in the order given, from the links a request sent."""
    return [models.ItemLink(label=link.label, url=link.url, position=position) for position, link in enumerate(links)]


def create_item(db: Session, list_id: int, item: schemas.ItemCreate):
    db_item = models.Item(
        list_id=list_id,
        sort_order=_next_sort_order(db, list_id),
        links=_links_from(item.links),
        **item.model_dump(exclude={"links"}),
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def create_items(db: Session, list_id: int, names) -> list:
    """Create several items in one commit, one per name, appended in order."""
    first = _next_sort_order(db, list_id)
    db_items = [models.Item(list_id=list_id, name=name, sort_order=first + i) for i, name in enumerate(names)]
    db.add_all(db_items)
    db.commit()
    for db_item in db_items:
        db.refresh(db_item)
    return db_items


def reorder_items(db: Session, list_id: int, item_ids) -> bool:
    """Give the listed items positions 0..n-1 in the order given. False (and
    nothing changed) if any id is repeated or isn't an item of this list."""
    if len(set(item_ids)) != len(item_ids):
        return False
    rows = {
        row.id: row
        for row in db.query(models.Item).filter(models.Item.list_id == list_id, models.Item.id.in_(item_ids))
    }
    if len(rows) != len(item_ids):
        return False
    for position, item_id in enumerate(item_ids):
        rows[item_id].sort_order = position
    db.commit()
    return True


def update_item(db: Session, db_item: models.Item, updates: schemas.ItemUpdate):
    fields = updates.model_dump(exclude_unset=True)
    if "links" in fields:
        fields.pop("links")
        if updates.links is not None:
            first_before = db_item.url
            db_item.links = _links_from(updates.links)
            if (updates.links[0].url if updates.links else None) != first_before:
                # The preview belongs to the primary link; a different one
                # makes what was fetched for the old one misleading.
                db_item.scrape_status = models.ScrapeStatus.not_started
                db_item.scraped_title = None
                db_item.scraped_description = None
                db_item.scraped_image_url = None
                db_item.scraped_at = None
                db_item.scrape_error = None
    if "done" in fields:
        # Track when an item was checked off so the UI can show it, and
        # clear it again if someone un-checks the box.
        db_item.done_at = datetime.utcnow() if fields["done"] else None
    if "list_id" in fields and fields["list_id"] != db_item.list_id:
        # Moved to another list: land at the end of it. A recipient has to
        # come from the new list's owner's contacts, so one that doesn't
        # (a different owner) is cleared rather than leaking across address books.
        db_item.sort_order = _next_sort_order(db, fields["list_id"])
        recipient_id = fields["recipient_id"] if "recipient_id" in fields else db_item.recipient_id
        if recipient_id is not None and not contact_usable_for_list(db, recipient_id, fields["list_id"]):
            fields["recipient_id"] = None
    for field, value in fields.items():
        setattr(db_item, field, value)
    db.commit()
    db.refresh(db_item)
    return db_item


def delete_item(db: Session, db_item: models.Item) -> None:
    db.delete(db_item)
    db.commit()


def save_scrape_result(
    db: Session,
    item_id: int,
    status: models.ScrapeStatus,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    error: Optional[str] = None,
):
    db_item = get_item(db, item_id)
    if db_item is None:
        return None
    db_item.scrape_status = status
    db_item.scraped_title = title
    db_item.scraped_description = description
    db_item.scraped_image_url = image_url
    db_item.scrape_error = error
    db_item.scraped_at = datetime.utcnow()
    db.commit()
    db.refresh(db_item)
    return db_item
