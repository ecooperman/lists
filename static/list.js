// A single list's page (list.html?id=N): edit the list itself, and add /
// edit / check off the items in it.

const params = new URLSearchParams(window.location.search);
const listId = Number(params.get("id"));
const LIST_API = `/api/lists/${listId}`;
const ITEMS_API = "/api/items";
const CONTACTS_API = "/api/contacts";

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

function renderListHeader() {
  document.getElementById("list-title").textContent = currentList.name;
  document.getElementById("list-purpose").textContent = currentList.purpose || "";
  document.getElementById("list-locked").classList.toggle("hidden", !currentList.locked);
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

  showBtn.addEventListener("click", () => {
    form.name.value = currentList.name;
    form.purpose.value = currentList.purpose || "";
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
        body: JSON.stringify({ name, purpose: form.purpose.value.trim() || null, locked: form.locked.checked }),
      });
      renderListHeader();
      syncDeleteButton();
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
  const remaining = items.filter((i) => !i.done).length;
  count.textContent = items.length ? `${remaining} left` : "";
  emptyState.hidden = items.length !== 0;
  for (const item of items) {
    list.appendChild(itemCardElement(item));
  }
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

  const dateLabel = Global.formatDateBadge(item.needed_by);
  if (dateLabel) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  }

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });

  Global.wireAccordionToggle(card, summary, details);

  card.append(summary, details);
  details.appendChild(buildItemDetails(card, item));
  return card;
}

function buildItemDetails(card, item) {
  const wrap = Global.el("div", { class: "item-details-inner" });

  const nameInput = Global.el("input", { type: "text", value: item.name, required: "required" });
  const recipientSelect = Global.el("select", {});
  populateRecipientSelect(recipientSelect, item.recipient_id);
  const listSelect = Global.el("select", {});
  for (const l of allLists) {
    const option = Global.el("option", { value: String(l.id), text: l.name });
    if (l.id === item.list_id) option.selected = true;
    listSelect.appendChild(option);
  }
  const descInput = Global.el("textarea", { rows: "2" });
  descInput.value = item.description || "";
  const urlInput = Global.el("input", { type: "url", value: item.url || "" });
  const dateInput = Global.el("input", { type: "date", value: Global.toISODate(item.needed_by) });

  const fields = Global.el("div", { class: "item-fields" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Who is it for?" }), recipientSelect]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "List" }), listSelect]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Needed by" }), dateInput]),
  ]);
  wrap.appendChild(fields);

  if (item.url) {
    wrap.appendChild(buildScrapeSection(card, item));
  }

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

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        Global.showMessage("Name is required.", "error");
        return;
      }
      try {
        const updated = await Global.fetchJSON(`${ITEMS_API}/${item.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            recipient_id: recipientSelect.value ? Number(recipientSelect.value) : null,
            list_id: Number(listSelect.value),
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            needed_by: Global.dateInputToISO(dateInput.value),
          }),
        });
        if (updated.list_id !== listId) {
          const target = allLists.find((l) => l.id === updated.list_id);
          Global.showMessage(`Moved "${name}" to ${target ? target.name : "another list"}.`, "success");
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

  actions.append(deleteBtn, saveBtn);
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

async function init() {
  if (!Number.isInteger(listId) || listId <= 0) {
    Global.showMessage("No list selected - pick one from the Lists page.", "error");
    return;
  }
  initEditListForm();
  initImportForm();
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
