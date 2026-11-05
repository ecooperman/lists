// A single list's page (list.html?id=N): edit the list itself, and add /
// edit / check off the items in it.

const params = new URLSearchParams(window.location.search);
const listId = Number(params.get("id"));
const LIST_API = `/api/lists/${listId}`;

let sortable = null;
let currentList = null;
let categories = [];
let categoriesById = {};
let allLists = [];
let contacts = [];
let contactsById = {};

const contactName = ItemCard.contactName;

// What an item card (item-card.js) needs to know about the page it's on.
const itemCtx = {
  get list() {
    return currentList;
  },
  get lists() {
    // Moving an item needs edit access to where it's going.
    return allLists.filter((l) => l.my_role !== "view" || l.id === listId);
  },
  get contacts() {
    return contacts;
  },
  get canEdit() {
    return canEdit();
  },
  reload: () => loadItems(),
};

// What you can do here follows from your role on this list (currentList.my_role):
// "owner" can do everything, "edit" works with the items, "view" only reads.
function canEdit() {
  return currentList.my_role !== "view";
}

function isOwner() {
  return currentList.my_role === "owner";
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

// A list offers its owner's contacts (names only), whoever is looking.
async function loadContacts() {
  contacts = await Global.fetchJSON(`${LIST_API}/contacts`);
  contactsById = Object.fromEntries(contacts.map((c) => [c.id, c]));
  populateRecipientSelect(document.getElementById("new-recipient"));
}

// --- this list (header, edit form) ---

// Priority is a fixed 1-5 number on every list (null = not set); each list
// only chooses what to call 1-5 (currentList.priority_labels, which the
// server always sends fully resolved with its defaults).
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
  const category = currentList.category_id ? categoriesById[currentList.category_id] : null;
  document.getElementById("list-category-slot").replaceChildren(...(category ? [categoryPill(category)] : []));
  document.getElementById("sort-mode").value = currentList.sort_mode;
  applyRole();
  const newPriority = document.getElementById("new-priority");
  populatePrioritySelect(newPriority, Number(newPriority.value) || null);
  document.title = `${currentList.name} - Lists`;
}

const ROLE_TEXT = { edit: "You can edit this list", view: "You can only view this list" };

// Show only what this person's role allows. (The server enforces it too;
// this just keeps the page from offering things that would be refused.)
function applyRole() {
  const owner = isOwner();
  const access = document.getElementById("list-access");
  access.textContent = owner ? "" : `Owned by ${currentList.owner_email} - ${ROLE_TEXT[currentList.my_role]}`;
  access.classList.toggle("hidden", owner);
  document.getElementById("show-edit-list").classList.toggle("hidden", !owner);
  document.getElementById("leave-list").classList.toggle("hidden", owner);
  if (!owner) document.getElementById("edit-list-form").classList.add("hidden");
  document.getElementById("show-import").classList.toggle("hidden", !canEdit());
  document.getElementById("show-add-item").classList.toggle("hidden", !canEdit());
  if (!canEdit()) document.getElementById("new-item-form").classList.add("hidden");
  document.getElementById("sort-mode").disabled = !canEdit();
}

async function loadList() {
  [currentList, allLists, categories] = await Promise.all([
    Global.fetchJSON(LIST_API),
    Global.fetchJSON("/api/lists"),
    Global.fetchJSON("/api/categories"),
  ]);
  categoriesById = Object.fromEntries(categories.map((c) => [c.id, c]));
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
    form.category_id.replaceChildren(
      Global.el("option", { value: "", text: "No category" }),
      ...categories.map((c) => Global.el("option", { value: String(c.id), text: c.name }))
    );
    form.category_id.value = currentList.category_id ? String(currentList.category_id) : "";
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
          category_id: form.category_id.value ? Number(form.category_id.value) : null,
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

// --- who has access (owner), leaving (everyone else) ---

const ROLE_LABELS = { owner: "Owner", edit: "Can edit", view: "Can view" };

function initSharing() {
  const memberList = document.getElementById("member-list");
  const inviteList = document.getElementById("invite-list");
  const emailInput = document.getElementById("member-email");
  const roleSelect = document.getElementById("member-role");
  const prompt = document.getElementById("invite-prompt");
  const promptText = document.getElementById("invite-prompt-text");
  const requestBtn = document.getElementById("invite-request");

  const send = (url, method, body) =>
    Global.fetchJSON(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });

  async function loadMembers() {
    let members;
    try {
      members = await Global.fetchJSON(`${LIST_API}/members`);
    } catch (err) {
      Global.showMessage(err.message, "error");
      return;
    }
    memberList.replaceChildren(
      ...members.map((member) => {
        const row = Global.el("div", { class: "member-row" }, [Global.el("span", { class: "member-email", text: member.email })]);
        if (member.role === "owner") {
          row.appendChild(Global.el("span", { class: "item-badge item-badge-muted", text: ROLE_LABELS.owner }));
          return row;
        }
        const select = Global.el(
          "select",
          { "aria-label": `Access for ${member.email}` },
          ["view", "edit"].map((role) => Global.el("option", { value: role, text: ROLE_LABELS[role] }))
        );
        select.value = member.role;
        select.addEventListener("change", async () => {
          try {
            await send(`${LIST_API}/members/${member.user_id}`, "PATCH", { role: select.value });
          } catch (err) {
            select.value = member.role;
            Global.showMessage(err.message, "error");
            return;
          }
          member.role = select.value;
        });
        const remove = Global.el("button", { type: "button", class: "cancel-btn", text: "Remove" });
        remove.addEventListener("click", async () => {
          if (!confirm(`Remove ${member.email}'s access to "${currentList.name}"?`)) return;
          try {
            await send(`${LIST_API}/members/${member.user_id}`, "DELETE");
            loadMembers();
          } catch (err) {
            Global.showMessage(err.message, "error");
          }
        });
        row.append(select, remove);
        return row;
      })
    );
  }

  // Requests for people with no account yet: waiting for an administrator, or
  // turned down. (Approved ones are people on the list by then.)
  async function loadInvites() {
    let invites;
    try {
      invites = await Global.fetchJSON(`${LIST_API}/invites`);
    } catch (err) {
      Global.showMessage(err.message, "error");
      return;
    }
    inviteList.replaceChildren(
      ...invites.map((invite) => {
        const pending = invite.status === "pending";
        const row = Global.el("div", { class: "member-row" }, [
          Global.el("span", { class: "member-email", text: `${invite.email} - ${ROLE_LABELS[invite.role].toLowerCase()}` }),
          Global.el("span", { class: "item-badge item-badge-muted", text: pending ? "Awaiting approval" : "Declined" }),
        ]);
        if (pending) {
          const withdraw = Global.el("button", { type: "button", class: "cancel-btn", text: "Withdraw" });
          withdraw.addEventListener("click", async () => {
            try {
              await send(`${LIST_API}/invites/${invite.id}`, "DELETE");
              loadInvites();
            } catch (err) {
              Global.showMessage(err.message, "error");
            }
          });
          row.appendChild(withdraw);
        }
        return row;
      })
    );
  }

  document.getElementById("show-edit-list").addEventListener("click", () => {
    loadMembers();
    loadInvites();
  });

  function hidePrompt() {
    prompt.classList.add("hidden");
    prompt.classList.remove("is-error");
  }

  // Say why an add or a request didn't go through, right under the box being
  // typed in (the page-wide message sits at the top, out of sight down here).
  function showProblem(text) {
    promptText.textContent = text;
    requestBtn.classList.add("hidden");
    prompt.classList.add("is-error");
    prompt.classList.remove("hidden");
  }

  // The box held someone with no account: say so, and offer to ask for them.
  async function offerInvite() {
    let left = null;
    try {
      left = (await Global.fetchJSON("/api/me")).invites_left;
    } catch (err) {
      // fall through: the server enforces the limit anyway
    }
    const none = left === 0;
    promptText.textContent = none
      ? "That person can't sign in yet, and you've used all your invites."
      : "That person can't sign in yet. You can ask for them to be let in - an administrator has to approve it." +
        (left === null ? "" : ` You have ${left} invite${left === 1 ? "" : "s"} left.`);
    requestBtn.classList.toggle("hidden", none);
    prompt.classList.remove("is-error");
    prompt.classList.remove("hidden");
  }

  async function addPerson() {
    const email = emailInput.value.trim();
    if (!email) return;
    hidePrompt();
    let res;
    try {
      // Raw fetch (not Global.fetchJSON): a 404 here means "no such person
      // yet", which is a prompt rather than an error.
      res = await fetch(`${LIST_API}/members`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, role: roleSelect.value }),
      });
    } catch (err) {
      showProblem("Couldn't reach the server - check your connection and try again.");
      return;
    }
    if (res.ok) {
      emailInput.value = "";
      Global.showMessage(`${email} now has access.`, "success");
      loadMembers();
    } else if (res.status === 404) {
      offerInvite();
    } else {
      const body = await res.json().catch(() => ({}));
      showProblem(typeof body.detail === "string" ? body.detail : Global.friendlyStatus(res.status));
    }
  }

  document.getElementById("member-add").addEventListener("click", addPerson);
  requestBtn.addEventListener("click", async () => {
    const email = emailInput.value.trim();
    try {
      const invite = await send(`${LIST_API}/invites`, "POST", { email, role: roleSelect.value });
      Global.showMessage(
        invite.status === "approved"
          ? `${invite.email} has been let in and added.`
          : `Requested. ${invite.email} will be added once it's approved.`,
        "success"
      );
    } catch (err) {
      showProblem(err.message);
      return;
    }
    emailInput.value = "";
    hidePrompt();
    loadMembers();
    loadInvites();
  });
  // Changing the address makes the offer about the old one stale.
  emailInput.addEventListener("input", hidePrompt);
  // Enter in the box adds rather than saving the whole form.
  emailInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addPerson();
    }
  });

  document.getElementById("leave-list").addEventListener("click", async () => {
    if (!confirm(`Leave "${currentList.name}"? You'll lose access until ${currentList.owner_email} adds you again.`)) return;
    try {
      const me = await Global.fetchJSON("/api/me");
      await send(`${LIST_API}/members/${me.id}`, "DELETE");
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
  if (sortable) sortable.option("disabled", currentList.sort_mode === "priority" || !canEdit());
  const remaining = items.filter((i) => !i.done).length;
  count.textContent = items.length ? `${remaining} left` : "";
  emptyState.hidden = items.length !== 0;
  emptyState.textContent = canEdit() ? "No items yet - add one above to get started." : "No items yet.";
  for (const item of items) {
    list.appendChild(ItemCard.create(item, itemCtx));
  }
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
  initSharing();
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
