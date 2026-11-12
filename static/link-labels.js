// Link Labels page: add, rename, reorder and delete the labels offered in the
// dropdown on an item's links. Same shape as the Categories page, minus the
// colors. A link keeps its own copy of its label's text, so changing a label
// here never changes a link that already uses it.

const LINK_LABELS_API = "/api/link-labels";

function linkLabelRowElement(label) {
  const handle = Global.el("span", { class: "category-drag-handle", "aria-label": `Drag to reorder "${label.name}"`, text: "⋮⋮" });
  const nameInput = Global.el("input", { type: "text", value: label.name, maxlength: "40", "aria-label": "Label" });

  const saveBtn = Global.el("button", {
    type: "button",
    class: "save-btn",
    text: "Save",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) {
        Global.showMessage("A label needs a name.", "error");
        return;
      }
      try {
        await Global.fetchJSON(`${LINK_LABELS_API}/${label.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        Global.showMessage(`Saved "${name}".`, "success");
        loadLinkLabels();
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
      if (!confirm(`Delete the label "${label.name}"? Links already using it keep their wording.`)) return;
      try {
        await Global.fetchJSON(`${LINK_LABELS_API}/${label.id}`, { method: "DELETE" });
        Global.showMessage(`Deleted "${label.name}".`, "success");
        loadLinkLabels();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    },
  });

  return Global.el("div", { class: "category-row", "data-id": String(label.id) }, [handle, nameInput, saveBtn, deleteBtn]);
}

async function loadLinkLabels() {
  const container = document.getElementById("link-label-rows");
  const labels = await Global.withLoading(container, Global.fetchJSON(LINK_LABELS_API));
  container.innerHTML = "";
  if (!labels.length) {
    container.appendChild(Global.el("p", { class: "empty-state", text: "No link labels yet - add one below." }));
    return;
  }
  for (const label of labels) container.appendChild(linkLabelRowElement(label));
}

// Drag by the handle; the new order is saved as soon as you drop. Not
// reloaded afterwards, so unsaved edits in other rows aren't lost.
function initReorder() {
  if (typeof Sortable === "undefined") {
    console.warn("SortableJS didn't load - drag-to-reorder is unavailable.");
    return;
  }
  const container = document.getElementById("link-label-rows");
  Sortable.create(container, {
    handle: ".category-drag-handle",
    draggable: ".category-row",
    animation: 150,
    forceFallback: true,
    async onEnd(evt) {
      if (evt.oldIndex === evt.newIndex) return;
      const orderedIds = [...container.querySelectorAll(".category-row")].map((row) => Number(row.dataset.id));
      try {
        await Global.fetchJSON(`${LINK_LABELS_API}/reorder`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ordered_ids: orderedIds }),
        });
      } catch (err) {
        Global.showMessage(err.message, "error");
        loadLinkLabels();
      }
    },
  });
}

function initAddForm() {
  const form = document.getElementById("add-link-label-form");
  const nameInput = document.getElementById("new-link-label-name");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return;
    try {
      await Global.fetchJSON(LINK_LABELS_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      nameInput.value = "";
      Global.showMessage(`Added "${name}".`, "success");
      loadLinkLabels();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

initReorder();
initAddForm();
loadLinkLabels().catch((err) => Global.showMessage(err.message, "error"));
