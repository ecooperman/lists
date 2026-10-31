// Lists index (index.html): every list, with a count of what's left in it,
// plus the add-list form. Each list is an accordion that expands into its
// items as the same cards the list's own page shows (item-card.js): edit,
// check off, delete or drag them into a new order without leaving this page.
// Adding items, importing and the list's settings are on its own page
// (list.html?id=N, list.js), linked from inside the expanded card.

// --- view preferences (per device, so kept in localStorage) ---

function loadPref(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch (e) {
    return fallback;
  }
}

function savePref(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    // private mode / storage blocked: the view just won't be remembered
  }
}

let lists = [];
let categories = [];
let categoriesById = {};
let listsSort = loadPref("lists.sort", "category"); // "category" (grouped under headings) | "manual" (flat)
let categoryFilter = loadPref("lists.categoryFilter", []); // category ids as strings, "none" = uncategorized
let contacts = null; // loaded the first time a list is expanded
// What's on screen per list id, so a change to one list's items can update its
// header count (and any other open list an item was moved into).
const listViews = new Map();
let listsSortable = null; // the flat view's
let groupSortables = []; // one per category group in the grouped view

async function loadLists() {
  const container = document.getElementById("lists-list");
  [lists, categories] = await Global.withLoading(container, Promise.all([Global.fetchJSON("/api/lists"), Global.fetchJSON("/api/categories")]));
  categoriesById = Object.fromEntries(categories.map((c) => [c.id, c]));
  // Forget filter entries for categories deleted since last visit.
  categoryFilter = categoryFilter.filter((id) => id === "none" || categoriesById[id]);
  buildCategoryFilter();
  renderLists();
}

// The lists as currently shown: filtered by category, then ordered by the
// manual order or grouped by category (in the Categories page's order,
// uncategorized last, ties in manual order).
function visibleLists() {
  let shown = lists;
  if (categoryFilter.length) {
    shown = shown.filter((l) => categoryFilter.includes(l.category_id ? String(l.category_id) : "none"));
  }
  if (listsSort === "category") {
    const rank = (l) => {
      const index = categories.findIndex((c) => c.id === l.category_id);
      return index === -1 ? categories.length : index;
    };
    shown = [...shown].sort((a, b) => rank(a) - rank(b) || a.sort_order - b.sort_order || a.id - b.id);
  }
  return shown;
}

// Grouped view: a heading per category (in the Categories page's order) with
// its lists under it, uncategorized last. Needs at least one category to make
// sense of; with none, the flat list is all there is to show.
function isGrouped() {
  return listsSort === "category" && categories.length > 0;
}

function categoryHeading(category, count) {
  return Global.el("h3", { class: "category-heading" }, [
    category ? categoryPill(category) : Global.el("span", { class: "category-heading-none", text: "No category" }),
    Global.el("span", { class: "category-heading-count", text: String(count) }),
  ]);
}

// `reopenId` re-renders with that list's card already expanded - used when a
// category change moves a list under a different heading, so it doesn't snap shut.
function renderLists({ reopenId = null } = {}) {
  const container = document.getElementById("lists-list");
  const shown = visibleLists();
  const grouped = isGrouped();
  const filtered = categoryFilter.length > 0;

  groupSortables.forEach((sortable) => sortable.destroy());
  groupSortables = [];
  listViews.clear();
  container.replaceChildren();

  if (grouped) {
    const groups = [
      ...categories.map((category) => ({ category, members: shown.filter((l) => l.category_id === category.id) })),
      { category: null, members: shown.filter((l) => !l.category_id || !categoriesById[l.category_id]) },
    ];
    for (const { category, members } of groups) {
      if (!members.length) continue;
      container.appendChild(categoryHeading(category, members.length));
      const group = Global.el("div", { class: "item-list lists-group" });
      for (const itemList of members) {
        group.appendChild(listCardElement(itemList, { showPill: false, expanded: itemList.id === reopenId }));
      }
      container.appendChild(group);
      groupSortables.push(makeListsSortable(group));
    }
  } else {
    for (const itemList of shown) {
      container.appendChild(listCardElement(itemList, { showPill: true, expanded: itemList.id === reopenId }));
    }
  }

  document.getElementById("list-count").textContent = !lists.length ? "" : filtered ? `${shown.length} of ${lists.length}` : String(lists.length);
  const empty = document.getElementById("empty-state");
  empty.hidden = shown.length !== 0;
  empty.textContent = lists.length ? "No lists in the selected categories." : "No lists yet - add one above to get started.";

  // Flat view: dragging saves the manual order of *every* list, so it's only
  // offered when the screen is exactly that order (not filtered to a subset).
  // Grouped view: each group reorders only its own lists (saveListOrder), which
  // is safe even with a filter on - a category's lists are all shown or all hidden.
  container.classList.toggle("no-reorder", !grouped && filtered);
  if (listsSortable) listsSortable.option("disabled", grouped || filtered);
}

function buildCategoryFilter() {
  const mount = document.getElementById("category-filter-mount");
  mount.replaceChildren();
  if (!categories.length) return; // nothing to filter by until a category exists
  mount.appendChild(
    Global.buildMultiSelect({
      options: [...categories.map((c) => ({ value: String(c.id), label: c.name, color: c.color })), { value: "none", label: "No category" }],
      selected: categoryFilter,
      placeholder: "All categories",
      onChange(selected) {
        categoryFilter = selected;
        savePref("lists.categoryFilter", categoryFilter);
        renderLists();
      },
    })
  );
}

function initListControls() {
  const sortSelect = document.getElementById("lists-sort");
  sortSelect.value = listsSort;
  sortSelect.addEventListener("change", () => {
    listsSort = sortSelect.value;
    savePref("lists.sort", listsSort);
    renderLists();
  });
}

// Persist a reorder. `ids` is the new order of the lists that were in the
// dragged container: all of them in the flat view, or one category's lists in
// the grouped view. They're slotted back into the positions they already held
// in the global manual order, so lists in other groups never move.
async function saveListOrder(ids) {
  const ordered = [...lists].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  const members = new Set(ids);
  let next = 0;
  const listIds = ordered.map((l) => (members.has(l.id) ? ids[next++] : l.id));
  try {
    await Global.fetchJSON("/api/lists/order", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ list_ids: listIds }),
    });
    // Keep the local copy in step so a later re-render (sort/filter change)
    // doesn't snap back to the old order.
    listIds.forEach((id, position) => {
      const row = lists.find((l) => l.id === id);
      if (row) row.sort_order = position;
    });
    lists.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  } catch (err) {
    Global.showMessage(err.message, "error");
    loadLists();
  }
}

// Drag-to-reorder by the handle at the left of each header (SortableJS, same
// approach as the item lists). Groups are separate sortables with no shared
// `group` option, so a list can't be dragged under a different heading - that's
// what the category dropdown in the expanded card is for.
function makeListsSortable(container) {
  if (typeof Sortable === "undefined") return { destroy() {}, option() {} };
  return Sortable.create(container, {
    handle: ".list-drag-handle",
    draggable: ".item-card",
    animation: 150,
    forceFallback: true,
    onEnd(evt) {
      if (evt.oldIndex === evt.newIndex) return;
      saveListOrder([...container.querySelectorAll(":scope > .item-card")].map((card) => Number(card.dataset.id)));
    },
  });
}

function initListsSortable() {
  if (typeof Sortable === "undefined") {
    console.warn("SortableJS didn't load - drag-to-reorder is unavailable.");
    return;
  }
  listsSortable = makeListsSortable(document.getElementById("lists-list"));
}

function listCardElement(itemList, { showPill = true, expanded = false } = {}) {
  const card = Global.el("div", { class: "item-card", "data-id": itemList.id });

  const preview = Global.el("div", { class: "list-preview" });

  // Category: a plain dropdown that saves when you pick (safe on touch too,
  // unlike click-to-edit text). Hidden until at least one category exists.
  const categorySelect = Global.el(
    "select",
    { "aria-label": "Category" },
    [Global.el("option", { value: "", text: "No category" }), ...categories.map((c) => Global.el("option", { value: String(c.id), text: c.name }))]
  );
  categorySelect.value = itemList.category_id ? String(itemList.category_id) : "";
  categorySelect.addEventListener("change", async () => {
    const previous = itemList.category_id ? String(itemList.category_id) : "";
    try {
      const updated = await Global.fetchJSON(`/api/lists/${itemList.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category_id: categorySelect.value ? Number(categorySelect.value) : null }),
      });
      itemList.category_id = updated.category_id;
      // Grouped by category, or filtered: the list may now belong under a
      // different heading (or not match the filter), so re-render - keeping
      // this card open. Otherwise just swap the pill in place.
      if (isGrouped() || categoryFilter.length) renderLists({ reopenId: itemList.id });
      else setCategoryPill(slot, itemList);
    } catch (err) {
      categorySelect.value = previous;
      Global.showMessage(err.message, "error");
    }
  });
  const categoryRow = categories.length
    ? Global.el("div", { class: "list-category-row" }, [Global.el("label", { text: "Category" }), categorySelect])
    : null;

  const details = Global.el("div", { class: "item-details hidden" }, [Global.el("div", { class: "item-details-inner" }, [categoryRow, preview])]);

  // Mouse devices: the name is click-to-edit in the header, and only the
  // right-hand zone (badges + chevron) expands the card - same layout as the
  // item rows on the list page. Touch: the whole row is the toggle button.
  const inlineHeader = typeof Global.inlineEdit === "function" && Global.supportsInlineEdit();
  const summary = inlineHeader
    ? Global.el("div", { class: "item-summary inline-header" })
    : Global.el("button", { type: "button", class: "item-summary", "aria-expanded": "false" });

  // The list's own drag handle (a different class from the item handles
  // inside the expanded preview, so the two sortables never grab each other).
  const handle = Global.el("span", { class: "list-drag-handle", "aria-label": `Drag to reorder "${itemList.name}"`, text: "⋮⋮" });
  handle.addEventListener("click", (e) => e.stopPropagation());
  summary.appendChild(handle);

  const purpose = itemList.purpose ? Global.el("span", { class: "list-summary-purpose", text: itemList.purpose }) : null;
  let right = summary;
  if (inlineHeader) {
    summary.appendChild(
      Global.el("span", { class: "list-summary-text inline" }, [
        Global.inlineEdit({
          type: "text",
          value: itemList.name,
          required: true,
          requiredMessage: "A list needs a name.",
          className: "item-summary-title summary-title-edit",
          async onSave(raw) {
            const updated = await Global.fetchJSON(`/api/lists/${itemList.id}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: raw }),
            });
            itemList.name = updated.name;
            return updated.name;
          },
        }),
        purpose,
      ])
    );
    summary.appendChild(Global.el("span", { class: "summary-spacer" }));
    right = Global.el("div", { class: "item-summary-zone", role: "button", tabindex: "0", "aria-label": "Expand or collapse", "aria-expanded": "false" });
    summary.appendChild(right);
  } else {
    summary.appendChild(
      Global.el("span", { class: "list-summary-text" }, [Global.el("span", { class: "item-summary-title", text: itemList.name }), purpose])
    );
  }

  // In the grouped view the heading already says which category this is.
  const slot = Global.el("span", { class: "category-slot" });
  if (showPill) {
    right.appendChild(slot);
    setCategoryPill(slot, itemList);
  }

  if (itemList.locked) {
    right.appendChild(Global.el("span", { class: "item-badge item-badge-muted", text: "Locked" }));
  }

  const countBadge = Global.el("span", { class: "item-badge item-badge-accent" });
  setCountBadge(countBadge, itemList);
  right.appendChild(countBadge);
  right.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  // `right` is what toggles the card: the zone on mouse devices, the whole
  // row on touch.
  Global.wireAccordionToggle(card, right, details);
  // Fetch the items each time the card opens, so it's never stale after
  // coming back from editing the list (handlers run in registration order,
  // so by here the toggle has already run).
  right.addEventListener("click", () => {
    if (card.classList.contains("expanded")) loadPreview(itemList, preview);
  });
  right.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && card.classList.contains("expanded")) loadPreview(itemList, preview);
  });

  card.append(summary, details);
  listViews.set(itemList.id, { card, countBadge, reloadPreview: () => loadPreview(itemList, preview) });

  if (expanded) {
    card.classList.add("expanded");
    details.classList.remove("hidden");
    right.setAttribute("aria-expanded", "true");
    loadPreview(itemList, preview);
  }
  return card;
}

// The category pill sits in a slot in the header so a category change can
// swap it in place, without re-rendering (and so collapsing) the card.
function setCategoryPill(slot, itemList) {
  const category = itemList.category_id ? categoriesById[itemList.category_id] : null;
  slot.replaceChildren(...(category ? [categoryPill(category)] : []));
}

function setCountBadge(badge, itemList) {
  badge.textContent = itemList.item_count ? `${itemList.open_count} left` : "Empty";
}

// After an edit in one list's items (checked off, deleted, moved to another
// list): bring the header counts back in step with the server. An open list
// whose items just changed because something was moved into it reloads too.
async function refreshCounts(editedId) {
  let fresh;
  try {
    fresh = await Global.fetchJSON("/api/lists");
  } catch (err) {
    console.error("Failed to refresh list counts", err);
    return;
  }
  for (const row of fresh) {
    const mine = lists.find((l) => l.id === row.id);
    if (!mine) continue;
    const changed = mine.item_count !== row.item_count || mine.open_count !== row.open_count;
    mine.item_count = row.item_count;
    mine.open_count = row.open_count;
    const view = listViews.get(row.id);
    if (!view) continue;
    setCountBadge(view.countBadge, mine);
    if (changed && row.id !== editedId && view.card.classList.contains("expanded")) view.reloadPreview();
  }
}

// A list's items as cards, in the same order the list page shows them, plus
// the way into the list page. In manual order they can be dragged into a new
// order right here (same rules as the list page).
async function loadPreview(itemList, preview) {
  let list, items;
  try {
    // Re-read the list itself along with its items: this page may be a stale
    // copy (browser Back), and dragging saves the *manual* order - so it must
    // never be offered for a list that has since been switched to priority.
    [list, items] = await Global.withLoading(
      preview,
      Promise.all([Global.fetchJSON(`/api/lists/${itemList.id}`), Global.fetchJSON(`/api/lists/${itemList.id}/items`), ensureContacts()])
    );
  } catch (err) {
    Global.showMessage(err.message, "error");
    return;
  }
  preview.innerHTML = "";

  const manual = list.sort_mode === "manual";
  if (!items.length) {
    preview.appendChild(Global.el("p", { class: "preview-empty", text: "No items yet." }));
  } else {
    // What an item card (item-card.js) needs to know about where it is.
    const ctx = {
      list,
      get lists() {
        return lists;
      },
      contacts,
      reload() {
        loadPreview(itemList, preview);
        refreshCounts(itemList.id);
      },
    };
    // Drag handles only make sense in manual mode (the .sort-priority class
    // hides them) - in priority mode the server decides the order.
    const stack = Global.el(
      "div",
      { class: "preview-list" + (manual ? "" : " sort-priority") },
      items.map((item) => ItemCard.create(item, ctx))
    );
    preview.appendChild(stack);
    if (manual) initPreviewSortable(itemList, preview, stack);
  }

  preview.appendChild(
    Global.el("div", { class: "preview-actions" }, [
      Global.el("a", { href: `list.html?id=${itemList.id}`, class: "secondary-btn", text: "Open list →" }),
    ])
  );
}

// Contacts feed the "who is it for" dropdown on each item. Fetched once; if it
// fails the dropdown just offers Unassigned rather than blocking the list.
async function ensureContacts() {
  if (contacts) return contacts;
  try {
    contacts = await Global.fetchJSON("/api/contacts");
  } catch (err) {
    console.error("Failed to load contacts", err);
    return [];
  }
  return contacts;
}

// Same drag rules as the list page (list.js initSortable): handle-only, done
// items aren't draggable and nothing drops among them, saved through the same
// order endpoint.
function initPreviewSortable(itemList, preview, stack) {
  if (typeof Sortable === "undefined") {
    console.warn("SortableJS didn't load - drag-to-reorder is unavailable.");
    return;
  }
  Sortable.create(stack, {
    handle: ".item-drag-handle",
    draggable: ".item-card:not(.done)",
    animation: 150,
    forceFallback: true,
    onMove: (evt) => !evt.related.classList.contains("done"),
    async onEnd(evt) {
      if (evt.oldIndex === evt.newIndex) return;
      const itemIds = [...stack.querySelectorAll(":scope > .item-card:not(.done)")].map((card) => Number(card.dataset.id));
      try {
        await Global.fetchJSON(`/api/lists/${itemList.id}/items/order`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ item_ids: itemIds }),
        });
      } catch (err) {
        Global.showMessage(err.message, "error");
        loadPreview(itemList, preview);
      }
    },
  });
}

function initAddListForm() {
  const form = document.getElementById("new-list-form");
  const showBtn = document.getElementById("show-add-list");
  const cancelBtn = document.getElementById("cancel-add-list");

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    document.getElementById("new-name").focus();
  });

  cancelBtn.addEventListener("click", () => {
    form.reset();
    form.classList.add("hidden");
    showBtn.classList.remove("hidden");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = form.name.value.trim();
    if (!name) return;
    try {
      await Global.fetchJSON("/api/lists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, purpose: form.purpose.value.trim() || null }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadLists();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

initListControls();
initListsSortable();
initAddListForm();
loadLists().catch((err) => Global.showMessage(err.message, "error"));
