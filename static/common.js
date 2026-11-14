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

const MONEY_FORMAT = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

// 123456 -> "$1,234.56"
function formatMoney(cents) {
  return MONEY_FORMAT.format((cents || 0) / 100);
}

// What an input holds for an amount: "1234.56" (no symbol or commas, so it edits cleanly); "" for none.
function centsToInput(cents) {
  return cents === null || cents === undefined ? "" : (cents / 100).toFixed(2);
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
