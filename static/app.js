const API_BASE = "/api/gifts";
const CONTACTS_API = "/api/contacts";

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

// --- gifts ---

async function loadGifts() {
  const gifts = await Global.fetchJSON(API_BASE);
  renderGifts(gifts);
}

function renderGifts(gifts) {
  const list = document.getElementById("gifts-list");
  const emptyState = document.getElementById("empty-state");
  const count = document.getElementById("gift-count");
  list.innerHTML = "";
  const remaining = gifts.filter((g) => !g.purchased).length;
  count.textContent = gifts.length ? `${remaining} to buy` : "";
  emptyState.hidden = gifts.length !== 0;
  for (const gift of gifts) {
    list.appendChild(giftCardElement(gift));
  }
}

// Each gift is a collapsed-by-default accordion: a single-line summary row
// (name, recipient, source domain, date) that expands into the full edit
// form in place - no separate "view" vs "edit" mode, and no modal. This
// mirrors the jobs admin page (jobs.html/jobs.js) in time-management, which
// solves the same "lots of rows, only show the full form for the one you're
// touching" problem the same way.
function giftCardElement(gift, { expanded = false } = {}) {
  const card = Global.el("div", {
    class: "item-card" + (expanded ? " expanded" : "") + (gift.purchased ? " done" : ""),
    "data-id": gift.id,
  });

  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });

  const purchasedCheckbox = Global.el("input", { type: "checkbox", class: "item-summary-done-toggle", "aria-label": "Mark purchased" });
  purchasedCheckbox.checked = !!gift.purchased;
  purchasedCheckbox.addEventListener("click", (e) => e.stopPropagation());
  purchasedCheckbox.addEventListener("change", async () => {
    try {
      await Global.fetchJSON(`${API_BASE}/${gift.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ purchased: purchasedCheckbox.checked }),
      });
      // Reload rather than patch the single card in place: purchased gifts
      // sort to the bottom (see crud.get_gifts), and the "N to buy" count
      // needs to stay in sync too.
      loadGifts();
    } catch (err) {
      purchasedCheckbox.checked = !purchasedCheckbox.checked;
      Global.showMessage(err.message, "error");
    }
  });
  summary.appendChild(purchasedCheckbox);

  summary.appendChild(Global.el("span", { class: "item-summary-title", text: gift.name }));

  const recipient = gift.recipient ? contactName(gift.recipient) : null;
  if (recipient) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-accent", text: recipient }));
  }

  const domain = gift.url ? Global.domainFromUrl(gift.url) : null;
  if (domain) {
    const domainLink = Global.el("a", {
      class: "item-badge item-badge-domain",
      href: gift.url,
      target: "_blank",
      rel: "noopener noreferrer",
      text: domain,
    });
    // Opening the source link shouldn't also toggle the accordion.
    domainLink.addEventListener("click", (e) => e.stopPropagation());
    summary.appendChild(domainLink);
  }

  const dateLabel = Global.formatDateBadge(gift.needed_by);
  if (dateLabel) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
  }

  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });

  Global.wireAccordionToggle(card, summary, details);

  card.append(summary, details);
  details.appendChild(buildGiftDetails(card, gift));
  return card;
}

function buildGiftDetails(card, gift) {
  const wrap = Global.el("div", { class: "item-details-inner" });

  const nameInput = Global.el("input", { type: "text", value: gift.name, required: "required" });
  const recipientSelect = Global.el("select", {});
  populateRecipientSelect(recipientSelect, gift.recipient_id);
  const descInput = Global.el("textarea", { rows: "2" });
  descInput.value = gift.description || "";
  const urlInput = Global.el("input", { type: "url", value: gift.url || "" });
  const dateInput = Global.el("input", { type: "date", value: Global.toISODate(gift.needed_by) });

  const fields = Global.el("div", { class: "item-fields" }, [
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Name" }), nameInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Who is it for?" }), recipientSelect]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Description" }), descInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "URL" }), urlInput]),
    Global.el("div", { class: "field" }, [Global.el("label", { text: "Needed by" }), dateInput]),
  ]);
  wrap.appendChild(fields);

  if (gift.url) {
    wrap.appendChild(buildScrapeSection(card, gift));
  }

  const actions = Global.el("div", { class: "item-actions" });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${gift.name}"?`)) return;
      await Global.fetchJSON(`${API_BASE}/${gift.id}`, { method: "DELETE" });
      card.remove();
      Global.showMessage(`Deleted "${gift.name}".`, "success");
      loadGifts();
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
        const updated = await Global.fetchJSON(`${API_BASE}/${gift.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            recipient_id: recipientSelect.value ? Number(recipientSelect.value) : null,
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            needed_by: Global.dateInputToISO(dateInput.value),
          }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        card.replaceWith(giftCardElement(updated, { expanded: true }));
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  actions.append(deleteBtn, saveBtn);
  wrap.appendChild(actions);
  return wrap;
}

function buildScrapeSection(card, gift) {
  const section = Global.el("div", { class: "scrape-section" });

  const scrapeBtn = Global.el("button", {
    type: "button",
    class: "scrape-btn",
    text: gift.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        const updated = await Global.fetchJSON(`${API_BASE}/${gift.id}/scrape`, { method: "POST" });
        card.replaceWith(giftCardElement(updated, { expanded: true }));
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        Global.showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapeStatus(gift));
  return section;
}

function renderScrapeStatus(gift) {
  if (gift.scrape_status === "success") {
    const preview = Global.el("div", { class: "scrape-preview" });
    if (gift.scraped_image_url) {
      preview.appendChild(Global.el("img", { src: gift.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = Global.el("div", { class: "scrape-text" });
    if (gift.scraped_title) textWrap.appendChild(Global.el("div", { class: "scrape-title", text: gift.scraped_title }));
    if (gift.scraped_description) textWrap.appendChild(Global.el("div", { class: "scrape-description", text: gift.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (gift.scrape_status === "failed") {
    return Global.el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${gift.scrape_error || "unknown error"}` });
  }
  if (gift.scrape_status === "unsupported") {
    return Global.el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return Global.el("div", { class: "scrape-note", text: "" });
}

function initAddGiftForm() {
  const form = document.getElementById("new-gift-form");
  const showBtn = document.getElementById("show-add-gift");
  const cancelBtn = document.getElementById("cancel-add-gift");

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
      await Global.fetchJSON(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadGifts();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

async function init() {
  initAddGiftForm();
  await loadContacts().catch((err) => console.error("Failed to load contacts", err));
  await loadGifts().catch((err) => console.error("Failed to load gifts", err));
}

init();
