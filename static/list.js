// A single list's page (list.html?id=N): edit the list itself, and add /
// edit / check off the items in it.

const params = new URLSearchParams(window.location.search);
const listId = Number(params.get("id"));
const LIST_API = `/api/lists/${listId}`;
const ITEMS_API = "/api/items";
const CONTACTS_API = "/api/contacts";

let sortable = null;
let currentList = null;
let allLists = [];
let contacts = [];
let contactsById = {};

function contactName(contact) {
  if (!contact) return null;
  return [contact.first_name, contact.last_name].filter(Boolean).join(" ");
}

// --- contacts (for the "who is it for" dropdowns) ---

function populateRecipientSelect(select, selectedId) {
  select.innerHTML = "";
  select.appendChild(Global.el("option", { value: "", text: "Unassigned" }));
  for (const contact of contacts) {
    const option = Global.el("option", { value: String(contact.id), text: contactName(contact) });
    if (selectedId && Number(selectedId) === contact.id) option.selected = true;
    select.appendChild(option);
  }
}

async function loadContacts() {
  contacts = await Global.fetchJSON(CONTACTS_API);
  contactsById = Object.fromEntries(contacts.map((c) => [c.id, c]));
  populateRecipientSelect(document.getElementById("new-recipient"));
}

// --- this list (header, edit form) ---

// Priority is a fixed 1-5 number on every list (null = not set); each list
// only chooses what to call 1-5 (currentList.priority_labels, which the
// server always sends fully resolved with its defaults).
function priorityLabel(level) {
  return currentList.priority_labels[level - 1];
}

function populatePrioritySelect(select, selected) {
  select.innerHTML = "";
  select.appendChild(Global.el("option", { value: "", text: "None" }));
  currentList.priority_labels.forEach((label, i) => {
    const option = Global.el("option", { value: String(i + 1), text: label });
    if (i + 1 === selected) option.selected = true;
    select.appendChild(option);
  });
}

function renderListHeader() {
  document.getElementById("list-title").textContent = currentList.name;
  document.getElementById("list-purpose").textContent = currentList.purpose || "";
  document.getElementById("list-locked").classList.toggle("hidden", !currentList.locked);
  document.getElementById("sort-mode").value = currentList.sort_mode;
  const newPriority = document.getElementById("new-priority");
  populatePrioritySelect(newPriority, Number(newPriority.value) || null);
  document.title = `${currentList.name} - Lists`;
}

async function loadList() {
  [currentList, allLists] = await Promise.all([Global.fetchJSON(LIST_API), Global.fetchJSON("/api/lists")]);
  renderListHeader();
}

function initEditListForm() {
  const form = document.getElementById("edit-list-form");
  const showBtn = document.getElementById("show-edit-list");
  const deleteBtn = document.getElementById("delete-list");

  function close() {
    form.classList.add("hidden");
    showBtn.classList.remove("hidden");
  }

  // Deleting is off while the list is (saved as) locked - uncheck the box
  // and Save first.
  function syncDeleteButton() {
    deleteBtn.disabled = currentList.locked;
    deleteBtn.title = currentList.locked ? "Unlock this list before deleting it" : "";
  }

  const labelInputs = document.getElementById("priority-label-inputs");
  function fillLabelInputs() {
    labelInputs.innerHTML = "";
    currentList.priority_labels.forEach((label, i) => {
      labelInputs.appendChild(
        Global.el("div", { class: "priority-label-row" }, [
          Global.el("span", { class: "priority-label-level", text: String(i + 1) }),
          Global.el("input", { type: "text", maxlength: "30", value: label, "aria-label": `Priority level ${i + 1} label` }),
        ])
      );
    });
  }

  document.getElementById("reset-priority-labels").addEventListener("click", async () => {
    try {
      currentList = await Global.fetchJSON(LIST_API, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ priority_labels: null }),
      });
      fillLabelInputs();
      renderListHeader();
      loadItems();
      Global.showMessage("Priority labels reset to the defaults.", "success");
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  showBtn.addEventListener("click", () => {
    form.name.value = currentList.name;
    form.purpose.value = currentList.purpose || "";
    fillLabelInputs();
    form.locked.checked = currentList.locked;
    syncDeleteButton();
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    form.name.focus();
  });

  document.getElementById("cancel-edit-list").addEventListener("click", close);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = form.name.value.trim();
    if (!name) return;
    try {
      currentList = await Global.fetchJSON(LIST_API, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          purpose: form.purpose.value.trim() || null,
          locked: form.locked.checked,
          priority_labels: [...labelInputs.querySelectorAll("input")].map((input) => input.value.trim()),
        }),
      });
      renderListHeader();
      syncDeleteButton();
      loadItems(); // badges and dropdowns use the (possibly renamed) labels
      close();
      Global.showMessage(`Saved "${name}".`, "success");
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  deleteBtn.addEventListener("click", async () => {
    try {
      // Re-fetch: the lock state and item count on the page may be stale
      // (another tab, or items added since load).
      const fresh = await Global.fetchJSON(LIST_API);
      if (fresh.locked) {
        currentList = fresh;
        renderListHeader();
        syncDeleteButton();
        Global.showMessage("This list is locked - unlock it before deleting it.", "error");
        return;
      }
      const count = fresh.item_count;
      const noun = count === 1 ? "item" : "items";
      const warning = count
        ? `"${fresh.name}" has ${count} ${noun}. Deleting the list permanently deletes ${count === 1 ? "that item" : `all ${count} items`} too - this can't be undone.\n\nDelete "${fresh.name}" and its ${count} ${noun}?`
        : `Delete the list "${fresh.name}"?`;
      if (!confirm(warning)) return;
      // force only when the user just confirmed deleting items; an empty
      // list deletes without it, so the server's guard still protects
      // against items added in the meantime.
      await Global.fetchJSON(count ? `${LIST_API}?force=true` : LIST_API, { method: "DELETE" });
      window.location.href = "/";
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

// --- import pasted notes as items ---

function initImportForm() {
  const form = document.getElementById("import-form");
  const showBtn = document.getElementById("show-import");
  const preview = document.getElementById("import-preview");
  const confirmBtn = document.getElementById("import-confirm");

  // Any edit to the text makes the shown preview stale.
  function resetPreview() {
    preview.classList.add("hidden");
    preview.innerHTML = "";
    confirmBtn.classList.add("hidden");
  }

  function close() {
    form.reset();
    resetPreview();
    form.classList.add("hidden");
    showBtn.classList.remove("hidden");
  }

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    form.text.focus();
  });

  document.getElementById("cancel-import").addEventListener("click", close);
  form.text.addEventListener("input", resetPreview);

  // Submit = "Preview": ask the server what the text parses into, show it,
  // and only then offer the Import button.
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = form.text.value;
    if (!text.trim()) return;
    try {
      const rows = await Global.fetchJSON(`${LIST_API}/items/import/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      preview.innerHTML = "";
      if (!rows.length) {
        preview.appendChild(Global.el("p", { class: "import-empty", text: "No items found - start each item on its own line with a dash." }));
      } else {
        preview.appendChild(Global.el("p", { class: "import-summary", text: `${rows.length} ${rows.length === 1 ? "item" : "items"} will be added:` }));
        preview.appendChild(
          Global.el(
            "ol",
            { class: "import-list" },
            rows.map((row) => Global.el("li", { text: row.name }))
          )
        );
        confirmBtn.textContent = `Import ${rows.length} ${rows.length === 1 ? "item" : "items"}`;
        confirmBtn.classList.remove("hidden");
      }
      preview.classList.remove("hidden");
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  confirmBtn.addEventListener("click", async () => {
    confirmBtn.disabled = true;
    try {
      const created = await Global.fetchJSON(`${LIST_API}/items/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: form.text.value }),
      });
      close();
      Global.showMessage(`Imported ${created.length} ${created.length === 1 ? "item" : "items"}.`, "success");
      loadItems();
    } catch (err) {
      Global.showMessage(err.message, "error");
    } finally {
      confirmBtn.disabled = false;
    }
  });
}

// --- items ---

async function loadItems() {
  const items = await Global.withLoading(document.getElementById("items-list"), Global.fetchJSON(`${LIST_API}/items`));
  renderItems(items);
}

function renderItems(items) {
  const list = document.getElementById("items-list");
  const emptyState = document.getElementById("empty-state");
  const count = document.getElementById("item-count");
  list.innerHTML = "";
  // Drag handles only make sense in manual mode - in priority mode the
  // server decides the order.
  list.classList.toggle("sort-priority", currentList.sort_mode === "priority");
  if (sortable) sortable.option("disabled", currentList.sort_mode === "priority");
  const remaining = items.filter((i) => !i.done).length;
  count.textContent = items.length ? `${remaining} left` : "";
  emptyState.hidden = items.length !== 0;
  for (const item of items) {
    list.appendChild(itemCardElement(item));
  }
}

// Progress is drawn as a background fill across the item's summary row (see
// the --progress rule in style.css) plus a small "N%" badge. A done item
// shows neither - checking it off supersedes progress - though its stored
// value is left alone.
function applyProgress(card, item, pct) {
  card.style.setProperty("--progress", item.done ? "0%" : `${pct}%`);
  const badge = card.querySelector(".item-badge-progress");
  badge.textContent = `${pct}%`;
  badge.classList.toggle("hidden", item.done || pct === 0);
}

// "Dec 25, 2026" for a plain YYYY-MM-DD value (inline-edit display only; the
// summary row's date badge stays the short "Dec 25").
function formatLongDate(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

// One definition per editable item field, used by both ways of editing it
// (see buildItemDetails). `get` reads the field off an item as the string an
// input holds; `toApi` turns what the input holds into the PATCH value.
function itemFieldDefs() {
  const contactOptions = [{ value: "", label: "Unassigned" }, ...contacts.map((c) => ({ value: String(c.id), label: contactName(c) }))];
  const priorityOptions = [{ value: "", label: "None" }, ...currentList.priority_labels.map((label, i) => ({ value: String(i + 1), label }))];
  const listOptions = allLists.map((l) => ({ value: String(l.id), label: l.name }));
  return [
    { key: "name", label: "Name", type: "text", required: true, requiredMessage: "Name is required.", get: (it) => it.name, toApi: (v) => v },
    { key: "recipient_id", label: "Who is it for?", type: "select", options: contactOptions, get: (it) => (it.recipient_id ? String(it.recipient_id) : ""), toApi: (v) => (v ? Number(v) : null) },
    { key: "priority", label: "Priority", type: "select", options: priorityOptions, get: (it) => (it.priority ? String(it.priority) : ""), toApi: (v) => (v ? Number(v) : null) },
    { key: "list_id", label: "List", type: "select", options: listOptions, get: (it) => String(it.list_id), toApi: (v) => Number(v) },
    { key: "description", label: "Description", type: "textarea", get: (it) => it.description || "", toApi: (v) => v || null },
    { key: "url", label: "URL", type: "url", get: (it) => it.url || "", toApi: (v) => v || null },
    { key: "needed_by", label: "Needed by", type: "date", format: formatLongDate, get: (it) => Global.toISODate(it.needed_by), toApi: (v) => Global.dateInputToISO(v) },
  ];
}

// The ordinary form control for a field (touch devices, see buildItemDetails).
function formInput(def, value) {
  let input;
  if (def.type === "select") {
    input = Global.el("select", {}, def.options.map((o) => Global.el("option", { value: o.value, text: o.label })));
  } else if (def.type === "textarea") {
    input = Global.el("textarea", { rows: "2" });
  } else {
    input = Global.el("input", { type: def.type });
  }
  input.value = value;
  return input;
}

function readFormInput(def, input) {
  return def.type === "select" || def.type === "date" ? input.value : input.value.trim();
}

// The summary row's contents. Rebuilt in place (refreshSummary) whenever an
// item's fields change - inline editing saves one field at a time, and
// re-rendering the whole card each time would steal focus from the field
// you just tabbed into.
function renderSummary(card, summary, item) {
  summary.replaceChildren();

  const doneCheckbox = Global.el("input", { type: "checkbox", class: "item-summary-done-toggle", "aria-label": "Mark done" });
  doneCheckbox.checked = !!item.done;
  doneCheckbox.addEventListener("click", (e) => e.stopPropagation());
  doneCheckbox.addEventListener("change", async () => {
    try {
      await Global.fetchJSON(`${ITEMS_API}/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ done: doneCheckbox.checked }),
      });
      // Reload rather than patch the single card in place: done items sort to
      // the bottom (see crud.get_items), and the "N left" count needs to
      // stay in sync too.
      loadItems();
    } catch (err) {
      doneCheckbox.checked = !doneCheckbox.checked;
      Global.showMessage(err.message, "error");
    }
  });
  if (!item.done) {
    // Grabbing the row anywhere would fight tap-to-expand, so dragging is
    // handle-only (see initSortable).
    const handle = Global.el("span", { class: "item-drag-handle", "aria-label": "Drag to reorder", text: "⋮⋮" });
    handle.addEventListener("click", (e) => e.stopPropagation());
    summary.appendChild(handle);
  }
  summary.appendChild(doneCheckbox);

  summary.appendChild(Global.el("span", { class: "item-summary-title", text: item.name }));

  const recipient = item.recipient ? contactName(item.recipient) : null;
  if (recipient) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-accent", text: recipient }));
  }

  const domain = item.url ? Global.domainFromUrl(item.url) : null;
  if (domain) {
    const domainLink = Global.el("a", {
      class: "item-badge item-badge-domain",
      href: item.url,
      target: "_blank",
      rel: "noopener noreferrer",
      text: domain,
    });
    // Opening the source link shouldn't also toggle the accordion.
    domainLink.addEventListener("click", (e) => e.stopPropagation());
    summary.appendChild(domainLink);
  }

  if (item.priority && !item.done) {
    summary.appendChild(
      Global.el("span", { class: `item-badge item-badge-priority priority-${item.priority}`, text: priorityLabel(item.priority) })
    );
  }

  summary.appendChild(Global.el("span", { class: "item-badge item-badge-muted item-badge-progress hidden" }));

  const dateLabel = Global.formatDateBadge(item.needed_by);
  if (dateLabel) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  }

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));
}

function refreshSummary(card, item) {
  card.classList.toggle("done", !!item.done);
  renderSummary(card, card.querySelector(".item-summary"), item);
  applyProgress(card, item, item.progress);
}

// Each item is a collapsed-by-default accordion: a single-line summary row
// (name, recipient, source domain, date) that expands into the full edit
// form in place - no separate "view" vs "edit" mode, and no modal. This
// mirrors the jobs admin page (jobs.html/jobs.js) in time-management, which
// solves the same "lots of rows, only show the full form for the one you're
// touching" problem the same way.
function itemCardElement(item, { expanded = false } = {}) {
  const card = Global.el("div", {
    class: "item-card" + (expanded ? " expanded" : "") + (item.done ? " done" : ""),
    "data-id": item.id,
  });

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
  renderSummary(card, summary, item);

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });

  Global.wireAccordionToggle(card, summary, details);

  card.append(summary, details);
  applyProgress(card, item, item.progress);
  details.appendChild(buildItemDetails(card, item));
  return card;
}

// The expanded card has two ways to edit, chosen per device:
//  - mouse (Global.supportsInlineEdit): each field reads as text, click to
//    edit, leaving the field saves just that field, Esc cancels. No Save
//    button.
//  - touch (and if the shared helper isn't loaded): the classic form - every
//    field an input, one Save button. Tap-to-edit fights scrolling on a
//    phone and blur-saves misfire when the keyboard dismisses.
function buildItemDetails(card, item) {
  const wrap = Global.el("div", { class: "item-details-inner" });
  const defs = itemFieldDefs();
  const inline = typeof Global.inlineEdit === "function" && Global.supportsInlineEdit();

  const patchItem = (body) =>
    Global.fetchJSON(`${ITEMS_API}/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

  // The scrape preview is only shown while the item has a URL, so inline
  // edits of the URL need to be able to rebuild just this part.
  const scrapeHost = Global.el("div");
  function renderScrape() {
    scrapeHost.replaceChildren();
    if (item.url) scrapeHost.appendChild(buildScrapeSection(card, item));
  }

  // Steps of 10 rather than free entry. Dragging fills the row live ("input"
  // fires continuously); the value is saved on its own when you let go
  // ("change"), so it doesn't need the Save button or re-render the card.
  const progressInput = Global.el("input", { type: "range", min: "0", max: "100", step: "10" });
  progressInput.value = String(item.progress);
  const progressValue = Global.el("span", { class: "progress-value", text: `${item.progress}%` });
  progressInput.addEventListener("input", () => {
    progressValue.textContent = `${progressInput.value}%`;
    applyProgress(card, item, Number(progressInput.value));
  });
  progressInput.addEventListener("change", async () => {
    try {
      const updated = await patchItem({ progress: Number(progressInput.value) });
      item.progress = updated.progress;
    } catch (err) {
      progressInput.value = String(item.progress);
      progressValue.textContent = `${item.progress}%`;
      applyProgress(card, item, item.progress);
      Global.showMessage(err.message, "error");
    }
  });

  // Where does the item belong after a save? Returns true if the page
  // reloaded the whole list (so this card is gone or about to be replaced).
  function reloadedAfterSave(updated, name) {
    if (updated.list_id !== listId) {
      const target = allLists.find((l) => l.id === updated.list_id);
      Global.showMessage(`Moved "${name}" to ${target ? target.name : "another list"}.`, "success");
      loadItems();
      return true;
    }
    return false;
  }

  const fields = Global.el("div", { class: "item-fields" });
  let saveBtn = null;

  if (inline) {
    for (const def of defs) {
      const field = Global.inlineEdit({
        type: def.type,
        value: def.get(item),
        options: def.options,
        required: def.required,
        requiredMessage: def.requiredMessage,
        format: def.format,
        async onSave(raw) {
          const updated = await patchItem({ [def.key]: def.toApi(raw) });
          Object.assign(item, updated);
          if (reloadedAfterSave(updated, item.name)) return def.get(updated);
          if (def.key === "priority" && currentList.sort_mode === "priority") {
            // Priority decides the order in this mode, so the item may belong elsewhere now.
            loadItems();
            return def.get(updated);
          }
          refreshSummary(card, item);
          if (def.key === "url") renderScrape();
          return def.get(updated);
        },
      });
      fields.appendChild(Global.el("div", { class: "field" }, [Global.el("label", { text: def.label }), field]));
    }
  } else {
    const inputs = Object.fromEntries(defs.map((def) => [def.key, formInput(def, def.get(item))]));
    for (const def of defs) {
      fields.appendChild(Global.el("div", { class: "field" }, [Global.el("label", { text: def.label }), inputs[def.key]]));
    }
    saveBtn = Global.el("button", {
      type: "button",
      class: "save-btn",
      text: "Save",
      onclick: async () => {
        const name = readFormInput(defs[0], inputs.name);
        if (!name) {
          Global.showMessage("Name is required.", "error");
          return;
        }
        try {
          const body = Object.fromEntries(defs.map((def) => [def.key, def.toApi(readFormInput(def, inputs[def.key]))]));
          const updated = await patchItem(body);
          if (reloadedAfterSave(updated, name)) return;
          if (updated.priority !== item.priority && currentList.sort_mode === "priority") {
            // Priority decides the order in this mode, so the item may belong elsewhere now.
            Global.showMessage(`Saved "${name}".`, "success");
            loadItems();
            return;
          }
          Global.showMessage(`Saved "${name}".`, "success");
          card.replaceWith(itemCardElement(updated, { expanded: true }));
        } catch (err) {
          Global.showMessage(err.message, "error");
        }
      },
    });
  }

  fields.appendChild(
    Global.el("div", { class: "field" }, [
      Global.el("label", { text: "Progress" }),
      Global.el("div", { class: "progress-control" }, [progressInput, progressValue]),
    ])
  );
  wrap.appendChild(fields);

  renderScrape();
  wrap.appendChild(scrapeHost);

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${item.name}"?`)) return;
      await Global.fetchJSON(`${ITEMS_API}/${item.id}`, { method: "DELETE" });
      card.remove();
      Global.showMessage(`Deleted "${item.name}".`, "success");
      loadItems();
    },
  });

  actions.appendChild(deleteBtn);
  if (saveBtn) actions.appendChild(saveBtn);
  wrap.appendChild(actions);
  return wrap;
}

function buildScrapeSection(card, item) {
  const section = Global.el("div", { class: "scrape-section" });

  const scrapeBtn = Global.el("button", {
    type: "button",
    class: "scrape-btn",
    text: item.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        const updated = await Global.fetchJSON(`${ITEMS_API}/${item.id}/scrape`, { method: "POST" });
        card.replaceWith(itemCardElement(updated, { expanded: true }));
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Global.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapeStatus(item));
  return section;
}

function renderScrapeStatus(item) {
  if (item.scrape_status === "success") {
    const preview = Global.el("div", { class: "scrape-preview" });
    if (item.scraped_image_url) {
      preview.appendChild(Global.el("img", { src: item.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = Global.el("div", { class: "scrape-text" });
    if (item.scraped_title) textWrap.appendChild(Global.el("div", { class: "scrape-title", text: item.scraped_title }));
    if (item.scraped_description) textWrap.appendChild(Global.el("div", { class: "scrape-description", text: item.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (item.scrape_status === "failed") {
    return Global.el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${item.scrape_error || "unknown error"}` });
  }
  if (item.scrape_status === "unsupported") {
    return Global.el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return Global.el("div", { class: "scrape-note", text: "" });
}

function initAddItemForm() {
  const form = document.getElementById("new-item-form");
  const showBtn = document.getElementById("show-add-item");
  const cancelBtn = document.getElementById("cancel-add-item");

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
    const payload = {
      name,
      recipient_id: form.recipient_id.value ? Number(form.recipient_id.value) : null,
      priority: form.priority.value ? Number(form.priority.value) : null,
      description: form.description.value.trim() || null,
      url: form.url.value.trim() || null,
      needed_by: Global.dateInputToISO(form.needed_by.value),
    };
    try {
      await Global.fetchJSON(`${LIST_API}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadItems();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

// --- ordering ---

function initSortMode() {
  const select = document.getElementById("sort-mode");
  select.addEventListener("change", async () => {
    try {
      currentList = await Global.fetchJSON(LIST_API, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sort_mode: select.value }),
      });
      loadItems();
    } catch (err) {
      select.value = currentList.sort_mode;
      Global.showMessage(err.message, "error");
    }
  });
}

// Drag-to-reorder via SortableJS, handle-only. forceFallback uses Sortable's
// own pointer handling rather than native drag-and-drop, which doesn't work
// for touch and is flaky for a handle nested inside a <button>. Done items
// aren't draggable and nothing can be dropped among them - they always sit
// at the bottom.
function initSortable() {
  if (typeof Sortable === "undefined") {
    console.warn("SortableJS didn't load - drag-to-reorder is unavailable.");
    return;
  }
  sortable = Sortable.create(document.getElementById("items-list"), {
    handle: ".item-drag-handle",
    draggable: ".item-card:not(.done)",
    animation: 150,
    forceFallback: true,
    onMove: (evt) => !evt.related.classList.contains("done"),
    onEnd: saveOrder,
  });
}

async function saveOrder(evt) {
  if (evt.oldIndex === evt.newIndex) return;
  const itemIds = [...document.querySelectorAll("#items-list .item-card:not(.done)")].map((c) => Number(c.dataset.id));
  try {
    await Global.fetchJSON(`${LIST_API}/items/order`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_ids: itemIds }),
    });
  } catch (err) {
    Global.showMessage(err.message, "error");
    loadItems();
  }
}

async function init() {
  if (!Number.isInteger(listId) || listId <= 0) {
    Global.showMessage("No list selected - pick one from the Lists page.", "error");
    return;
  }
  initEditListForm();
  initImportForm();
  initSortMode();
  initSortable();
  initAddItemForm();
  try {
    await loadList();
  } catch (err) {
    // A bad/removed list id 404s here - nothing else on the page can work.
    Global.showMessage(err.message, "error");
    return;
  }
  await loadContacts().catch((err) => console.error("Failed to load contacts", err));
  await loadItems().catch((err) => console.error("Failed to load items", err));
}

init();
