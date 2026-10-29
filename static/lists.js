// Lists index (index.html): every list, with a count of what's left in it,
// plus the add-list form. Each list is an accordion that previews its items
// read-only; editing them happens on the list's own page (list.html?id=N,
// list.js), linked from inside the expanded card.

async function loadLists() {
  const container = document.getElementById("lists-list");
  const lists = await Global.withLoading(container, Global.fetchJSON("/api/lists"));
  container.innerHTML = "";
  document.getElementById("list-count").textContent = lists.length ? String(lists.length) : "";
  document.getElementById("empty-state").hidden = lists.length !== 0;
  for (const itemList of lists) {
    container.appendChild(listCardElement(itemList));
  }
}

function listCardElement(itemList) {
  const card = Global.el("div", { class: "item-card", "data-id": itemList.id });
  const summary = Global.el("button", { type: "button", class: "item-summary", "aria-expanded": "false" });

  summary.appendChild(
    Global.el("span", { class: "list-summary-text" }, [
      Global.el("span", { class: "item-summary-title", text: itemList.name }),
      itemList.purpose ? Global.el("span", { class: "list-summary-purpose", text: itemList.purpose }) : null,
    ])
  );

  if (itemList.locked) {
    summary.appendChild(Global.el("span", { class: "item-badge item-badge-muted", text: "Locked" }));
  }

  const countText = itemList.item_count ? `${itemList.open_count} left` : "Empty";
  summary.appendChild(Global.el("span", { class: "item-badge item-badge-accent", text: countText }));
  summary.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  const preview = Global.el("div", { class: "list-preview" });
  const details = Global.el("div", { class: "item-details hidden" }, [Global.el("div", { class: "item-details-inner" }, [preview])]);

  Global.wireAccordionToggle(card, summary, details);
  // Fetch the items each time the card opens, so it's never stale after
  // coming back from editing the list (handlers run in registration order,
  // so by here the toggle has already run).
  summary.addEventListener("click", () => {
    if (card.classList.contains("expanded")) loadPreview(itemList, preview);
  });
  summary.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && card.classList.contains("expanded")) loadPreview(itemList, preview);
  });

  card.append(summary, details);
  return card;
}

// Read-only view of a list's items, in the same order the list page shows
// them, plus the way into the list page where they can be changed.
async function loadPreview(itemList, preview) {
  let items;
  try {
    items = await Global.withLoading(preview, Global.fetchJSON(`/api/lists/${itemList.id}/items`));
  } catch (err) {
    Global.showMessage(err.message, "error");
    return;
  }
  preview.innerHTML = "";

  if (!items.length) {
    preview.appendChild(Global.el("p", { class: "preview-empty", text: "No items yet." }));
  } else {
    preview.appendChild(
      Global.el(
        "ul",
        { class: "preview-list" },
        items.map((item) => previewItemElement(itemList, item))
      )
    );
  }

  preview.appendChild(
    Global.el("div", { class: "preview-actions" }, [
      Global.el("a", { href: `list.html?id=${itemList.id}`, class: "secondary-btn", text: "Open list →" }),
    ])
  );
}

function previewItemElement(itemList, item) {
  const row = Global.el("li", { class: "preview-item" + (item.done ? " done" : "") }, [
    Global.el("span", { class: "preview-check", "aria-label": item.done ? "Done" : "Not done", text: item.done ? "✓" : "" }),
    Global.el("span", { class: "preview-name", text: item.name }),
  ]);
  if (item.priority && !item.done) {
    row.appendChild(
      Global.el("span", {
        class: `item-badge item-badge-priority priority-${item.priority}`,
        text: itemList.priority_labels[item.priority - 1],
      })
    );
  }
  if (item.progress && !item.done) {
    row.appendChild(Global.el("span", { class: "item-badge item-badge-muted", text: `${item.progress}%` }));
  }
  return row;
}

function initAddListForm() {
  const form = document.getElementById("new-list-form");
  const showBtn = document.getElementById("show-add-list");
  const cancelBtn = document.getElementById("cancel-add-list");

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
    try {
      await Global.fetchJSON("/api/lists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, purpose: form.purpose.value.trim() || null }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      Global.showMessage(`Added "${name}".`, "success");
      loadLists();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

initAddListForm();
loadLists().catch((err) => Global.showMessage(err.message, "error"));
