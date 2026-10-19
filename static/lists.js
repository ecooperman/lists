// Lists index (index.html): every list, with a count of what's left in it,
// plus the add-list form. Opening a list goes to list.html?id=N (list.js).

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

// The whole card is a link into the list - editing/deleting a list lives on
// the list's own page, so there's nothing to expand here.
function listCardElement(itemList) {
  const card = Global.el("div", { class: "item-card", "data-id": itemList.id });
  const link = Global.el("a", { class: "item-summary list-link", href: `list.html?id=${itemList.id}` });

  const text = Global.el("span", { class: "list-summary-text" }, [
    Global.el("span", { class: "item-summary-title", text: itemList.name }),
    itemList.purpose ? Global.el("span", { class: "list-summary-purpose", text: itemList.purpose }) : null,
  ]);
  link.appendChild(text);

  if (itemList.locked) {
    link.appendChild(Global.el("span", { class: "item-badge item-badge-muted", text: "Locked" }));
  }

  const countText = itemList.item_count ? `${itemList.open_count} left` : "Empty";
  link.appendChild(Global.el("span", { class: "item-badge item-badge-accent", text: countText }));
  link.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));

  card.appendChild(link);
  return card;
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
