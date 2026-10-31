// Helpers shared by the lists index, a single list's page and the categories
// page (needs Global from shared-assets' theme.js).

function applyCategoryColors(el, color, textColor) {
  el.style.setProperty("--cat-color", color);
  el.dataset.text = textColor;
}

// A category as a filled pill in its own colors (see .category-pill in
// style.css; text_color picks dark or light text so it reads on the fill).
function categoryPill(category) {
  const pill = Global.el("span", { class: "category-pill", text: category.name });
  applyCategoryColors(pill, category.color, category.text_color);
  return pill;
}
