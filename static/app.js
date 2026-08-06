const API_BASE = "/api/gifts";
const CONTACTS_API = "/api/contacts";

let contacts = [];
let contactsById = {};

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = `${url} -> ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (e) {
      // ignore, use default detail
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function showMessage(text, kind) {
  const el = document.getElementById("gift-message");
  el.textContent = text;
  el.className = "gift-message " + kind;
  clearTimeout(showMessage._t);
  showMessage._t = setTimeout(() => el.classList.add("hidden"), 4000);
}

function toISODate(isoDateTime) {
  if (!isoDateTime) return "";
  return isoDateTime.slice(0, 10);
}

function formatDateBadge(isoDateTime) {
  if (!isoDateTime) return null;
  const [y, m, d] = isoDateTime.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function domainFromUrl(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (e) {
    return null;
  }
}

function contactName(contact) {
  if (!contact) return null;
  return [contact.first_name, contact.last_name].filter(Boolean).join(" ");
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

// --- contacts (for the "who is it for" dropdowns) ---

function populateRecipientSelect(select, selectedId) {
  select.innerHTML = "";
  select.appendChild(el("option", { value: "", text: "Unassigned" }));
  for (const contact of contacts) {
    const option = el("option", { value: String(contact.id), text: contactName(contact) });
    if (selectedId && Number(selectedId) === contact.id) option.selected = true;
    select.appendChild(option);
  }
}

async function loadContacts() {
  contacts = await fetchJSON(CONTACTS_API);
  contactsById = Object.fromEntries(contacts.map((c) => [c.id, c]));
  populateRecipientSelect(document.getElementById("new-recipient"));
}

// --- gifts ---

async function loadGifts() {
  const gifts = await fetchJSON(API_BASE);
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
  const card = el("div", {
    class: "gift-card" + (expanded ? " expanded" : "") + (gift.purchased ? " purchased" : ""),
    "data-id": gift.id,
  });

  const summary = el("button", { type: "button", class: "gift-summary", "aria-expanded": String(expanded) });

  const purchasedCheckbox = el("input", { type: "checkbox", class: "gift-purchased-toggle", "aria-label": "Mark purchased" });
  purchasedCheckbox.checked = !!gift.purchased;
  purchasedCheckbox.addEventListener("click", (e) => e.stopPropagation());
  purchasedCheckbox.addEventListener("change", async () => {
    try {
      await fetchJSON(`${API_BASE}/${gift.id}`, {
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
      showMessage(err.message, "error");
    }
  });
  summary.appendChild(purchasedCheckbox);

  summary.appendChild(el("span", { class: "gift-summary-title", text: gift.name }));

  const recipient = gift.recipient ? contactName(gift.recipient) : null;
  if (recipient) {
    summary.appendChild(el("span", { class: "gift-summary-recipient", text: recipient }));
  }

  const domain = gift.url ? domainFromUrl(gift.url) : null;
  if (domain) {
    const domainLink = el("a", {
      class: "gift-summary-domain",
      href: gift.url,
      target: "_blank",
      rel: "noopener noreferrer",
      text: domain,
    });
    // Opening the source link shouldn't also toggle the accordion.
    domainLink.addEventListener("click", (e) => e.stopPropagation());
    summary.appendChild(domainLink);
  }

  const dateLabel = formatDateBadge(gift.needed_by);
  if (dateLabel) {
    summary.appendChild(el("span", { class: "gift-summary-date", text: dateLabel }));
  }

  summary.appendChild(el("span", { class: "gift-chevron", "aria-hidden": "true", text: "▸" }));

  const details = el("div", { class: "gift-details" + (expanded ? "" : " hidden") });

  summary.addEventListener("click", () => {
    const isExpanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !isExpanded);
    summary.setAttribute("aria-expanded", String(isExpanded));
  });

  card.append(summary, details);
  details.appendChild(buildGiftDetails(card, gift));
  return card;
}

function buildGiftDetails(card, gift) {
  const wrap = el("div", { class: "gift-details-inner" });

  const nameInput = el("input", { type: "text", value: gift.name, required: "required" });
  const recipientSelect = el("select", {});
  populateRecipientSelect(recipientSelect, gift.recipient_id);
  const descInput = el("textarea", { rows: "2" });
  descInput.value = gift.description || "";
  const urlInput = el("input", { type: "url", value: gift.url || "" });
  const dateInput = el("input", { type: "date", value: toISODate(gift.needed_by) });

  const fields = el("div", { class: "gift-fields" }, [
    el("div", { class: "field" }, [el("label", { text: "Name" }), nameInput]),
    el("div", { class: "field" }, [el("label", { text: "Who is it for?" }), recipientSelect]),
    el("div", { class: "field" }, [el("label", { text: "Description" }), descInput]),
    el("div", { class: "field" }, [el("label", { text: "URL" }), urlInput]),
    el("div", { class: "field" }, [el("label", { text: "Needed by" }), dateInput]),
  ]);
  wrap.appendChild(fields);

  if (gift.url) {
    wrap.appendChild(buildScrapeSection(card, gift));
  }

  const actions = el("div", { class: "gift-actions" });

  const deleteBtn = el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete "${gift.name}"?`)) return;
      await fetchJSON(`${API_BASE}/${gift.id}`, { method: "DELETE" });
      card.remove();
      showMessage(`Deleted "${gift.name}".`, "success");
      loadGifts();
    },
  });

  const saveBtn = el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        showMessage("Name is required.", "error");
        return;
      }
      try {
        const updated = await fetchJSON(`${API_BASE}/${gift.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            recipient_id: recipientSelect.value ? Number(recipientSelect.value) : null,
            description: descInput.value.trim() || null,
            url: urlInput.value.trim() || null,
            needed_by: dateInput.value ? `${dateInput.value}T00:00:00` : null,
          }),
        });
        showMessage(`Saved "${name}".`, "success");
        card.replaceWith(giftCardElement(updated, { expanded: true }));
      } catch (err) {
        showMessage(err.message, "error");
      }
    },
  });

  actions.append(deleteBtn, saveBtn);
  wrap.appendChild(actions);
  return wrap;
}

function buildScrapeSection(card, gift) {
  const section = el("div", { class: "gift-scrape-section" });

  const scrapeBtn = el("button", {
    type: "button",
    class: "scrape-btn",
    text: gift.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Fetching...";
      try {
        const updated = await fetchJSON(`${API_BASE}/${gift.id}/scrape`, { method: "POST" });
        card.replaceWith(giftCardElement(updated, { expanded: true }));
      } catch (err) {
        e.target.disabled = false;
        e.target.textContent = "Fetch preview";
        showMessage(`Preview fetch failed: ${err.message}`, "error");
      }
    },
  });
  section.appendChild(scrapeBtn);
  section.appendChild(renderScrapeStatus(gift));
  return section;
}

function renderScrapeStatus(gift) {
  if (gift.scrape_status === "success") {
    const preview = el("div", { class: "scrape-preview" });
    if (gift.scraped_image_url) {
      preview.appendChild(el("img", { src: gift.scraped_image_url, class: "scrape-image", alt: "" }));
    }
    const textWrap = el("div", { class: "scrape-text" });
    if (gift.scraped_title) textWrap.appendChild(el("div", { class: "scrape-title", text: gift.scraped_title }));
    if (gift.scraped_description) textWrap.appendChild(el("div", { class: "scrape-description", text: gift.scraped_description }));
    preview.appendChild(textWrap);
    return preview;
  }
  if (gift.scrape_status === "failed") {
    return el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${gift.scrape_error || "unknown error"}` });
  }
  if (gift.scrape_status === "unsupported") {
    return el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
  }
  return el("div", { class: "scrape-note", text: "" });
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
      needed_by: form.needed_by.value ? `${form.needed_by.value}T00:00:00` : null,
    };
    try {
      await fetchJSON(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      showMessage(`Added "${name}".`, "success");
      loadGifts();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });
}

async function init() {
  initAddGiftForm();
  await loadContacts().catch((err) => console.error("Failed to load contacts", err));
  await loadGifts().catch((err) => console.error("Failed to load gifts", err));
}

init();
