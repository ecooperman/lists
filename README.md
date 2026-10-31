# Lists

A small local app for keeping any number of named lists. Each list has a
name and a purpose ("Gifts", "Movies to watch", ...) and its own items; every
list has the same item structure - name, description, a source URL (e.g. a
product page), a date you need it by, who it's for, and a done checkbox.

(This started life as the `gifts` app - the existing gift items live on in a
list called "Gifts". The app's port is still `8030` from then, and the DB
file is still `gifts.db`.)

## Run it

```bash
cd lists
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.main
```

Then open http://127.0.0.1:8030 (host/port are set in `app/config.py`).

The SQLite database (`gifts.db`) is not created by the app itself - `alembic
upgrade head` creates it. This only needs to be run once for a fresh
install; see below for how schema changes are handled from here on.

## API-first design

The backend (`app/`) is a plain JSON REST API (`/api/gifts`, `/api/contacts`,
`/docs` for the interactive Swagger UI) with no knowledge of the frontend.
The frontend (`static/`) is a thin vanilla-JS client with no build step,
talking to the API over `fetch`. That separation means the backend can be
tested and used entirely on its own, and the frontend can later be swapped
for something richer without touching the API.

List endpoints:

- `GET /api/lists` - all lists in their manual order, each with `item_count`
  and `open_count`
- `PUT /api/lists/order` - body `{"list_ids": [...]}`; saves that order for the
  lists index (400 if an id repeats or doesn't exist)
- `POST /api/lists` - create a list (`name` required, `purpose` optional)
- `GET /api/lists/{id}` - fetch one list
- `PATCH /api/lists/{id}` - update `name` / `purpose` / `locked` / `category_id`
  (`null` clears it), plus
  `sort_mode` (`manual` or `priority`) and `priority_labels` (exactly five
  names for priority levels 1-5; a blank one falls back to its default, `null`
  resets all five). Every list response carries `priority_labels` fully
  resolved, so clients never need the defaults (Low, Medium, High, Critical,
  Blocker) themselves
- `DELETE /api/lists/{id}` - delete a list. 409s if the list is `locked`
  (unlock it first - `force` doesn't override this), or while it still has
  items (same guard as contacts) unless you pass `?force=true`, which deletes
  the items along with the list and returns `deleted_items`
- `GET /api/lists/{id}/items` - the list's items, not-done first, then by the
  list's `sort_mode`: `manual` (the drag order, default) or `priority`
  (highest first, items with no priority last, ties in manual order)
- `POST /api/lists/{id}/items` - add an item to the end of the list (`name` is
  the only required field)
- `PUT /api/lists/{id}/items/order` - body `{"item_ids": [...]}`; saves that
  order as the list's manual order (400 if an id repeats or isn't in the list)
- `POST /api/lists/{id}/items/import/preview` - body `{"text": "..."}`; returns
  the items that text would create, without saving anything
- `POST /api/lists/{id}/items/import` - same body; creates those items (400 if
  the text contains none)

Import format: every line starting with `-` starts a new item. Any non-dash
lines after it are treated as the same item wrapped onto another line (a stray
line break from copy/paste) and joined onto its name with a space. Text before
the first dash, blank lines, and `---` separators are ignored (see
`app/importer.py`).

Category endpoints (labels a list can belong to, managed on `/categories.html`):

- `GET /api/categories` - all categories in their manual order
- `POST /api/categories` - create one (`name`, `color` as `#rrggbb`, and
  `text_color` `dark`/`light`); appended to the end, 409 on a duplicate name
- `PATCH /api/categories/{id}` - rename / recolor
- `POST /api/categories/reorder` - body `{"ordered_ids": [...]}`
- `DELETE /api/categories/{id}` - 409s while any list still uses it

Item endpoints (acting on one existing item):

- `GET /api/items/{id}` - fetch one item
- `PATCH /api/items/{id}` - update any subset of fields, including
  `recipient_id`, `done`, `progress` (0-100), `priority` (1-5, or `null` for
  none) and `list_id` (moves the item to the end of another list; it can't be
  cleared - every item belongs to exactly one list)
- `DELETE /api/items/{id}` - delete an item
- `POST /api/items/{id}/scrape` - (re-)run the scraper for the item's URL and
  persist the result onto the item

Contact endpoints (the "who is it for" list, managed on `/contacts.html`):

- `GET /api/contacts` - list all contacts
- `POST /api/contacts` - create a contact (`first_name` is the only required
  field; `last_name`, `email`, `address` are optional)
- `PATCH /api/contacts/{id}` - update any subset of fields
- `DELETE /api/contacts/{id}` - delete a contact (409s if any item is still
  assigned to them - reassign or delete those items first)

## Schema changes (Alembic)

Schema is owned by migrations under `migrations/versions/`, not by wiping
`gifts.db`. To change the schema:

```bash
# 1. Edit app/models.py as usual
# 2. Generate a migration from the diff
alembic revision --autogenerate -m "short description"
# 3. Look over the generated file in migrations/versions/ - autogenerate
#    is good but not infallible (e.g. it won't detect a plain column rename
#    on its own)
# 4. Apply it
alembic upgrade head
```

This preserves existing data. Useful commands: `alembic current` (what
revision the db is at), `alembic check` (does the db match `models.py`
right now), `alembic downgrade -1` (undo the last migration).

SQLite can't `ALTER TABLE` to add a constraint directly, so
`migrations/env.py` has `render_as_batch=True` set, which makes autogenerate
wrap those changes in `op.batch_alter_table(...)` (SQLite rebuilds the table
under the hood). If autogenerate produces a `batch_op.create_foreign_key(None,
...)` / `drop_constraint(None, ...)` call, give it an explicit name in both
`upgrade()` and `downgrade()` - SQLite's batch mode needs a name to
reference, and will fail with `ValueError: Constraint must have a name`
otherwise.

## Upgrading to Postgres later

Everything goes through SQLAlchemy + Alembic, so moving off SQLite is mostly
a matter of swapping `DATABASE_URL` in `app/database.py` (and
`sqlalchemy.url` in `alembic.ini`) for a Postgres connection string,
installing a driver (`psycopg`), and running `alembic upgrade head` against
the new database - no application code depends on SQLite specifics.

## Scraping framework

`app/scraping/` holds the strategy framework for pulling a title, description,
and image out of an item's URL:

- `base.py` - `ScraperStrategy` interface (`matches(url)` / `scrape(url)`)
  and the `ScrapedContent` result shape
- `og_tags.py` - shared helper that fetches a page and reads its Open Graph
  meta tags (`og:title`, `og:description`, `og:image`); takes a
  `user_agent` override since Instagram/Facebook need a crawler UA to serve
  their server-rendered markup, while most other sites (retailers, in
  particular) just want a normal browser UA
- `instagram.py`, `facebook.py` - social-post strategies, matching on
  hostname and delegating to `og_tags` with the crawler UA
- `generic.py` - catch-all fallback for everything else (most item links are
  ordinary retailer product pages), delegating to `og_tags` with a normal
  browser UA
- `registry.py` - picks the first strategy whose `matches()` returns true
  for a given URL; `generic.py` is registered last since it matches
  everything
- `service.py` - orchestrates a scrape and persists the outcome (success,
  failed, or unsupported) onto the item via `crud.save_scrape_result`

Adding support for a site that needs special handling later is just a new
`ScraperStrategy` subclass registered ahead of `GenericScraper` in
`registry.py`.

Note: some sites (Instagram/Facebook among them) gate content behind a login
wall or block automated requests outright, so a scrape can legitimately come
back `failed` even though a strategy matched. That's surfaced back to the UI
rather than treated as a crash - scraping is a nice-to-have on top of the
manually-entered fields, never a requirement.

## Deploying

Runs as a systemd service on the Digital Ocean droplet, reached through a
Cloudflare Tunnel (no inbound ports opened on the droplet) and gated by
Cloudflare Access - see `deploy/lists.service`.

One-time setup on the droplet:

```bash
sudo mkdir -p /opt/apps/lists && sudo chown deploy:deploy /opt/apps/lists
# as the deploy user:
git clone https://github.com/ecooperman/lists.git /opt/apps/lists
cd /opt/apps/lists
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo cp deploy/lists.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lists
```

Then add an ingress entry for `127.0.0.1:8030` to `/etc/cloudflared/config.yml`,
route DNS for its hostname (`cloudflared tunnel route dns <tunnel-name>
<hostname>`), and add a Cloudflare Access policy for that hostname.

Ongoing deploys are automatic: `.github/workflows/deploy.yml` runs on every
push to `main` - it SSHes in, pulls, reinstalls dependencies, runs `alembic
upgrade head`, and restarts the service. Needs these repo secrets set once
(Settings -> Secrets and variables -> Actions): `DO_HOST`, `DO_USER` (the
`deploy` user), `DO_SSH_KEY` (that user's private key).

## Notes

- Pages: `/` is the lists index (each list with how many items are left; click
  one to expand its items, which are the same cards as on the list's own page:
  rename, check off, edit any field, delete or (in manual order) drag them into
  a new order right there - with an "Open list" link for adding or importing
  items and the list's settings),
  `/list.html?id=N` is one list's items (the same `page.html?id=N` pattern
  trip-planning uses), `/contacts.html` manages contacts and
  `/categories.html` manages categories. Editing,
  locking and deleting a list is the "Edit list" button on that list's own
  page; "Import items" is next to it.
- Categories (name, color, dark/light text, a drag order) are modeled on
  trip-planning's and time-management's, except a list has at most one. Set a
  list's from the dropdown inside its expanded card on the index (saves when
  you pick) or in "Edit list".
- The lists index has two views, chosen with the "Sort" dropdown (remembered
  per device in localStorage, not saved with any list):
  - **By category** (the default once at least one category exists): lists are
    grouped under a heading for each category, in the Categories page's order,
    with "No category" last; empty categories get no heading. The cards don't
    repeat the category, since the heading says it. Drag a list by its grip
    handle to reorder it *within* its category - the other categories' lists
    don't move, and a list can't be dragged under a different heading (use the
    category dropdown for that; the card stays open as it moves).
  - **Manual (flat)**: one list in your manual order, each card showing its
    category as a colored pill. Dragging here saves the order of every list, so
    it's only offered when the filter isn't narrowing what's shown.

  The category filter works in both views.
- A list can be locked: a locked list shows a "Locked" badge and its Delete
  button is disabled until you uncheck "Locked" and Save. Deleting an
  unlocked list that has items asks you to confirm and says how many items
  will be deleted with it; an empty list just asks for a plain confirm.
- Import is two steps - paste, "Preview" (shows exactly what will be created),
  then "Import N items" - so a bad paste never writes anything.
- Only `name` is required on an item - everything else (recipient,
  description, URL, needed-by date) is optional and can be filled in later.
- Items are collapsed-by-default accordion cards - the same pattern as the
  jobs admin page in time-management (`jobs.html`/`jobs.js`): a single-line
  summary (name, recipient, source domain, date) that expands in place into
  the full edit form, rather than a separate view/edit mode or a modal. The
  edit form's "List" dropdown moves the item to another list.
- Editing has two modes, chosen per device. With a mouse
  (`Global.supportsInlineEdit()`, from shared-assets) it's click-to-edit:
  - **Headers:** an item's (or, on the index, a list's) name in the
    accordion header is editable in place - click it, or Tab to it and press
    Enter - without expanding the card. Only the right-hand strip (badges and
    chevron) expands/collapses the card on a mouse device, and the gap between
    the title and that strip does nothing, so a click near the title can't
    expand instead of edit.
  - **Expanded fields:** each field in the expanded card also reads as text
    and edits the same way.
  - **Saving:** clicking away / Tab / Enter saves just that field, Esc
    cancels, a dropdown saves when you pick, and the summary row updates in
    place.

  On touch devices - where tap-to-edit competes with scrolling and a
  keyboard-dismiss would trigger a save - the whole header row is the
  expand/collapse button and the expanded card is the classic form with one
  Save button. Both are driven by the same field definitions in
  `itemFieldDefs()` in `static/item-card.js`, the module that builds an item's
  card for both the list page (`list.js`) and the expanded lists on the index
  (`lists.js`). Each page hands it a small context (the list, all lists, the
  contacts, and a `reload()`), so an item behaves the same in either place; on
  the index, checking off, deleting or moving an item also refreshes the
  header counts and any other open list it was moved into.
- "Add Item" is a toggle button that reveals an inline add form (again
  mirroring the jobs admin page's "+ Add New Job Opportunity"), not a modal.
- Ordering: each list is in manual order by default - drag an item by the
  grip handle at the left of its row (touch and mouse; done items stay at the
  bottom and can't be dragged). The same drag works on the lists index inside an
  expanded list; it re-reads the list's sort mode each time it opens, so a
  stale page can't overwrite the manual order. The "Sort" dropdown above the
  items switches the list to priority order, which is saved per list; the manual order is
  kept underneath and is what breaks ties, and dragging is off in that mode.
  New and imported items are added to the end of the list.
- Priority is a fixed 1-5 scale (an item may have none) so ordering means the
  same thing on every list, but each list names the levels itself: the
  defaults are Low, Medium, High, Critical, Blocker, and "Edit list" has five
  fields to rename them (or "Reset to defaults"). The item's badge, its
  dropdown and the index preview all show the list's own names.
- Progress: a slider (steps of 10) in the expanded item fills the item's row
  behind it and shows a percent badge; it saves on release and a done item
  hides it.
- Each item has a checkbox in its summary row to mark it done without
  expanding the card - done items sort to the bottom of the list and show
  with a struck-through name. `done_at` is recorded automatically when the
  checkbox is checked (and cleared if unchecked).
- "Who is it for?" is a dropdown of contacts, not a free-text field -
  contacts are managed separately on `/contacts.html` (linked from the nav
  bar), the same "categories" pattern used in time-management. Only
  `first_name` is required on a contact; `last_name`, `email`, and `address`
  are optional. A contact can't be deleted while an item still references
  them (409, mirroring the category-in-use check in time-management).
- The "Fetch preview" button only appears when an item has a URL, and calls
  `POST /api/items/{id}/scrape`. It can be re-run any time (e.g. after a
  transient failure) via "Re-fetch preview", and lives inside the expanded
  card alongside the scraped preview (if any).
- Every list shares the same item fields for now (including the gift-flavored
  "Who is it for?" / "Needed by"); per-list fields would be the next layer.
