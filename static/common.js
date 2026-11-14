// Wording under the "Who has access" box (the panel itself is shared-assets'
// access.js, which takes this as its `hint`).
const LIST_ACCESS_HINT =
  "Add someone who already uses the app, or ask for a new person to be let in - an administrator approves each request. " +
  "Viewers can read this list; editors can also change its items. " +
  "A person you add gets the category you filed it under copied into their own categories (they can change it freely; yours is never affected). " +
  "Only you can rename it, change who has access, lock it or delete it.";

// Helpers shared by the lists index, a single list's page and the categories
// page (needs Global from shared-assets' theme.js).

function applyCategoryColors(el, color, textColor) {
  el.style.setProperty("--cat-color", color);
  el.dataset.text = textColor;
}

// A category <select>: no category, then the person's own, then the way to make
// a new one without leaving the page (see askForCategory).
const ADD_CATEGORY = "__add__";

function fillCategorySelect(select, categories, categoryId) {
  select.replaceChildren(
    Global.el("option", { value: "", text: "No category" }),
    ...categories.map((c) => Global.el("option", { value: String(c.id), text: c.name })),
    Global.el("option", { value: ADD_CATEGORY, text: "Add new category..." })
  );
  select.value = categoryId ? String(categoryId) : "";
  select.dataset.chosen = select.value; // what to go back to if the new-category prompt is cancelled
}

// Makes a category from just a name (the server gives it a neutral colour; it
// can be recoloured on the Categories page) and adds it to `categories`. A name
// the person already has, in any capitalisation, is reused rather than refused.
// Resolves with the category, or null if it couldn't be made (the error is shown).
async function createCategoryNamed(name, categories) {
  const existing = categories.find((c) => c.name.toLowerCase() === name.toLowerCase());
  if (existing) return existing;
  try {
    const created = await Global.fetchJSON("/api/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    categories.push(created);
    return created;
  } catch (err) {
    Global.showMessage(err.message, "error");
    return null;
  }
}

// Call when `select` has "Add new category..." chosen: swaps it for a name box,
// then refills the select with the new category chosen (or puts it back as it
// was if cancelled). done(category) gets the category, or null.
function askForCategory(select, categories, done) {
  Global.askForName(
    select,
    { placeholder: "New category", submit: (name) => createCategoryNamed(name, categories) },
    (category) => {
      if (category) fillCategorySelect(select, categories, category.id);
      else select.value = select.dataset.chosen;
      done(category);
    }
  );
}

// A category as a filled pill in its own colors (see .category-pill in
// style.css; text_color picks dark or light text so it reads on the fill).
function categoryPill(category) {
  const pill = Global.el("span", { class: "category-pill", text: category.name });
  applyCategoryColors(pill, category.color, category.text_color);
  return pill;
}

// --- money (a list that tracks costs; amounts are whole cents on the server) ---

const MONEY_WITH_CENTS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const MONEY_WHOLE = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

// 123456 -> "$1,234.56"; a whole-dollar amount drops the cents: 75000 -> "$750"
function formatMoney(cents) {
  const amount = cents || 0;
  return (amount % 100 === 0 ? MONEY_WHOLE : MONEY_WITH_CENTS).format(amount / 100);
}

// What an input holds for an amount: "1234.56", or "750" for a whole-dollar one (no symbol or
// commas, so it edits cleanly); "" for none.
function centsToInput(cents) {
  if (cents === null || cents === undefined) return "";
  return cents % 100 === 0 ? String(cents / 100) : (cents / 100).toFixed(2);
}

// What someone typed ("$1,234.5", "12", "") -> whole cents, or null for blank.
// Throws a plain-English error for anything that isn't an amount.
function parseMoney(text) {
  const cleaned = String(text || "").replace(/[$,\s]/g, "");
  if (cleaned === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) throw new Error("Enter an amount like 25 or 24.99.");
  const cents = Math.round(parseFloat(cleaned) * 100);
  if (cents > 1_000_000_000) throw new Error("That amount is too large.");
  return cents;
}

// --- expand / collapse all ---
//
// One small button beside a page's count: it opens every card when any is closed, and closes them
// all once every one is open; its words and arrow follow the state. Each card is opened by the
// same click a person would make, so nothing about how a card opens is repeated here.
//   button    the .expand-all-btn element (an icon span and a .expand-all-label span inside)
//   cards()   the cards on the page right now (elements with the "expanded" class when open)
//   toggleOf  the element to click to open or close a given card
// Returns sync(): call it after the cards are (re)drawn. It also follows cards opened by hand.
function mountToggleAll(button, { cards, toggleOf, container, minimum = 2 }) {
  function sync() {
    const all = cards();
    button.classList.toggle("hidden", all.length < minimum);
    const allOpen = all.length > 0 && all.every((card) => card.classList.contains("expanded"));
    const label = allOpen ? "Collapse all" : "Expand all";
    button.querySelector(".expand-all-label").textContent = label;
    button.setAttribute("aria-label", label);
    const icon = button.querySelector(".btn-icon");
    icon.dataset.icon = allOpen ? "arrow-up" : "arrow-down";
    applyIcons(button);
  }
  button.addEventListener("click", () => {
    const all = cards();
    const open = !all.every((card) => card.classList.contains("expanded"));
    for (const card of all) {
      if (card.classList.contains("expanded") !== open) toggleOf(card).click();
    }
    sync();
  });
  // A card opened or closed by hand changes what the button should offer.
  const later = () => setTimeout(sync, 0);
  container.addEventListener("click", later);
  container.addEventListener("keydown", later);
  return sync;
}
