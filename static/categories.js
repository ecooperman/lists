// Categories page: create, rename, recolor, reorder and delete the labels a
// list can belong to. Same shape as the Contacts page, plus a drag order
// (what "sort by category" on the lists index follows).

const CATEGORIES_API = "/api/categories";

function updatePreview(pill, name, color, textColor) {
  pill.textContent = name.trim() || "Preview";
  applyCategoryColors(pill, color, textColor);
}

function categoryRowElement(category) {
  const handle = Global.el("span", { class: "category-drag-handle", "aria-label": `Drag to reorder "${category.name}"`, text: "⋮⋮" });
  const nameInput = Global.el("input", { type: "text", value: category.name, maxlength: "40", "aria-label": "Name" });
  const colorInput = Global.el("input", { type: "color", value: category.color, "aria-label": "Color" });
  const textSelect = Global.el(
    "select",
    { "aria-label": "Text color" },
    [Global.el("option", { value: "dark", text: "Dark text" }), Global.el("option", { value: "light", text: "Light text" })]
  );
  textSelect.value = category.text_color;
  const preview = Global.el("span", { class: "category-pill" });

  const refreshPreview = () => updatePreview(preview, nameInput.value, colorInput.value, textSelect.value);
  for (const input of [nameInput, colorInput, textSelect]) input.addEventListener("input", refreshPreview);
  refreshPreview();

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        Global.showMessage("A category needs a name.", "error");
        return;
      }
      try {
        await Global.fetchJSON(`${CATEGORIES_API}/${category.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, color: colorInput.value, text_color: textSelect.value }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        loadCategories();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  const deleteBtn = Global.el("button", {
    type: "button",
    class: "danger-btn",
    text: "Delete",
    onclick: async () => {
      if (!confirm(`Delete category "${category.name}"?`)) return;
      try {
        await Global.fetchJSON(`${CATEGORIES_API}/${category.id}`, { method: "DELETE" });
        Global.showMessage(`Deleted "${category.name}".`, "success");
        loadCategories();
      } catch (err) {
        // 409 while lists still use it - the server's message says so.
        Global.showMessage(err.message, "error");
      }
    },
  });

  return Global.el("div", { class: "category-row", "data-id": String(category.id) }, [handle, nameInput, colorInput, textSelect, preview, saveBtn, deleteBtn]);
}

async function loadCategories() {
  const container = document.getElementById("category-rows");
  const categories = await Global.withLoading(container, Global.fetchJSON(CATEGORIES_API));
  container.innerHTML = "";
  if (!categories.length) {
    container.appendChild(Global.el("p", { class: "empty-state", text: "No categories yet - add one below." }));
    return;
  }
  for (const category of categories) container.appendChild(categoryRowElement(category));
}

// Drag by the handle; the new order is saved as soon as you drop. Not
// reloaded afterwards, so unsaved edits in other rows aren't lost.
function initReorder() {
  if (typeof Sortable === "undefined") {
    console.warn("SortableJS didn't load - drag-to-reorder is unavailable.");
    return;
  }
  const container = document.getElementById("category-rows");
  Sortable.create(container, {
    handle: ".category-drag-handle",
    draggable: ".category-row",
    animation: 150,
    forceFallback: true,
    async onEnd(evt) {
      if (evt.oldIndex === evt.newIndex) return;
      const orderedIds = [...container.querySelectorAll(".category-row")].map((row) => Number(row.dataset.id));
      try {
        await Global.fetchJSON(`${CATEGORIES_API}/reorder`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ordered_ids: orderedIds }),
        });
      } catch (err) {
        Global.showMessage(err.message, "error");
        loadCategories();
      }
    },
  });
}

function initAddForm() {
  const form = document.getElementById("add-category-form");
  const nameInput = document.getElementById("new-category-name");
  const colorInput = document.getElementById("new-category-color");
  const textSelect = document.getElementById("new-category-text-color");
  const preview = document.getElementById("new-category-preview");

  const refresh = () => updatePreview(preview, nameInput.value, colorInput.value, textSelect.value);
  for (const input of [nameInput, colorInput, textSelect]) input.addEventListener("input", refresh);
  refresh();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return;
    try {
      await Global.fetchJSON(CATEGORIES_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, color: colorInput.value, text_color: textSelect.value }),
      });
      nameInput.value = "";
      refresh();
      Global.showMessage(`Added "${name}".`, "success");
      loadCategories();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

initReorder();
initAddForm();
loadCategories().catch((err) => Global.showMessage(err.message, "error"));
