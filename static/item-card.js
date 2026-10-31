// An item as an accordion card: a summary row that expands into an editor.
// Shared by a list's own page (list.js) and the expanded lists on the index
// (lists.js), so an item is edited the same way in both places. Needs Global
// from shared-assets' theme.js.
//
// Each page passes a `ctx` describing where the card lives:
//   ctx.list      the list the item is in (id, priority_labels, sort_mode)
//   ctx.lists     every list, for the "move to another list" field
//   ctx.contacts  every contact, for the "who is it for" field
//   ctx.reload()  re-fetch and re-render that list's items (called when an
//                 edit changes which items there are or in what order)
// They're read when a card is built, so a page can swap in new values by
// reassigning what the getters return.

const ItemCard = (function () {
  const ITEMS_API = "/api/items";

  function contactName(contact) {
    if (!contact) return null;
    return [contact.first_name, contact.last_name].filter(Boolean).join(" ");
  }

  // Progress is drawn as a background fill across the item's summary row (see
  // the --progress rule in style.css) plus a small "N%" badge. A done item
  // shows neither - checking it off supersedes progress - though its stored
  // value is left alone.
  function applyProgress(card, item, pct) {
    card.style.setProperty("--progress", item.done ? "0%" : `${pct}%`);
    const badge = card.querySelector(".item-badge-progress");
    badge.textContent = `${pct}%`;
    badge.classList.toggle("hidden", item.done || pct === 0);
  }

  // "Dec 25, 2026" for a plain YYYY-MM-DD value (inline-edit display only; the
  // summary row's date badge stays the short "Dec 25").
  function formatLongDate(isoDate) {
    const [y, m, d] = isoDate.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  // One definition per editable item field, used by both ways of editing it
  // (see buildItemDetails). `get` reads the field off an item as the string an
  // input holds; `toApi` turns what the input holds into the PATCH value.
  function itemFieldDefs(ctx) {
    const contactOptions = [{ value: "", label: "Unassigned" }, ...ctx.contacts.map((c) => ({ value: String(c.id), label: contactName(c) }))];
    const priorityOptions = [{ value: "", label: "None" }, ...ctx.list.priority_labels.map((label, i) => ({ value: String(i + 1), label }))];
    const listOptions = ctx.lists.map((l) => ({ value: String(l.id), label: l.name }));
    return [
      { key: "name", label: "Name", type: "text", required: true, requiredMessage: "Name is required.", get: (it) => it.name, toApi: (v) => v },
      { key: "recipient_id", label: "Who is it for?", type: "select", options: contactOptions, get: (it) => (it.recipient_id ? String(it.recipient_id) : ""), toApi: (v) => (v ? Number(v) : null) },
      { key: "priority", label: "Priority", type: "select", options: priorityOptions, get: (it) => (it.priority ? String(it.priority) : ""), toApi: (v) => (v ? Number(v) : null) },
      { key: "list_id", label: "List", type: "select", options: listOptions, get: (it) => String(it.list_id), toApi: (v) => Number(v) },
      { key: "description", label: "Description", type: "textarea", get: (it) => it.description || "", toApi: (v) => v || null },
      { key: "url", label: "URL", type: "url", get: (it) => it.url || "", toApi: (v) => v || null },
      { key: "needed_by", label: "Needed by", type: "date", format: formatLongDate, get: (it) => Global.toISODate(it.needed_by), toApi: (v) => Global.dateInputToISO(v) },
    ];
  }

  // The ordinary form control for a field (touch devices, see buildItemDetails).
  function formInput(def, value) {
    let input;
    if (def.type === "select") {
      input = Global.el("select", {}, def.options.map((o) => Global.el("option", { value: o.value, text: o.label })));
    } else if (def.type === "textarea") {
      input = Global.el("textarea", { rows: "2" });
    } else {
      input = Global.el("input", { type: def.type });
    }
    input.value = value;
    return input;
  }

  function readFormInput(def, input) {
    return def.type === "select" || def.type === "date" ? input.value : input.value.trim();
  }

  // True where click-to-edit is used: a mouse-style device with the shared
  // helper loaded (see buildItemDetails for why not on touch).
  function canInlineEdit() {
    return typeof Global.inlineEdit === "function" && Global.supportsInlineEdit();
  }

  function patchItem(item, body) {
    return Global.fetchJSON(`${ITEMS_API}/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  // The item's name as a click-to-edit title in the accordion header, so it
  // can be renamed without expanding the card.
  function summaryTitleField(card, item) {
    return Global.inlineEdit({
      type: "text",
      value: item.name,
      required: true,
      requiredMessage: "Name is required.",
      className: "item-summary-title summary-title-edit",
      async onSave(raw) {
        const updated = await patchItem(item, { name: raw });
        Object.assign(item, updated);
        // Keep the expanded form's own Name field (first inline field) in step.
        const formName = card.querySelector(":scope > .item-details .item-fields .inline-edit");
        if (formName && formName.setValue) formName.setValue(item.name);
        return updated.name;
      },
    });
  }

  // The summary row's contents. Rebuilt in place (refreshSummary) whenever an
  // item's fields change - inline editing saves one field at a time, and
  // re-rendering the whole card each time would steal focus from the field
  // you just tabbed into.
  //
  // Two layouts, by device (see summary's "inline-header" class):
  //  - mouse: the title is click-to-edit, and ONLY the right-hand cluster
  //    (badges + chevron, stretched to the card's edge) expands/collapses the
  //    card. The gap between them does nothing, so a stray click near the title
  //    can't expand the card instead of editing it.
  //  - touch: the whole row is the expand/collapse button, as before.
  function renderSummary(card, summary, item, details, ctx) {
    summary.replaceChildren();
    const inlineHeader = summary.classList.contains("inline-header");

    const doneCheckbox = Global.el("input", { type: "checkbox", class: "item-summary-done-toggle", "aria-label": "Mark done" });
    doneCheckbox.checked = !!item.done;
    doneCheckbox.addEventListener("click", (e) => e.stopPropagation());
    doneCheckbox.addEventListener("change", async () => {
      try {
        await patchItem(item, { done: doneCheckbox.checked });
        // Reload rather than patch the single card in place: done items sort to
        // the bottom (see crud.get_items), and the "N left" count needs to
        // stay in sync too.
        ctx.reload();
      } catch (err) {
        doneCheckbox.checked = !doneCheckbox.checked;
        Global.showMessage(err.message, "error");
      }
    });
    if (!item.done) {
      // Grabbing the row anywhere would fight tap-to-expand, so dragging is
      // handle-only (see list.js initSortable / lists.js initPreviewSortable).
      const handle = Global.el("span", { class: "item-drag-handle", "aria-label": "Drag to reorder", text: "⋮⋮" });
      handle.addEventListener("click", (e) => e.stopPropagation());
      summary.appendChild(handle);
    }
    summary.appendChild(doneCheckbox);

    // Everything right of the title goes in `right`: the toggle zone on mouse
    // devices, the row itself on touch.
    let right = summary;
    if (inlineHeader) {
      summary.appendChild(summaryTitleField(card, item));
      summary.appendChild(Global.el("span", { class: "summary-spacer" }));
      right = Global.el("div", {
        class: "item-summary-zone",
        role: "button",
        tabindex: "0",
        "aria-label": "Expand or collapse",
        "aria-expanded": String(card.classList.contains("expanded")),
      });
      summary.appendChild(right);
      Global.wireAccordionToggle(card, right, details);
    } else {
      summary.appendChild(Global.el("span", { class: "item-summary-title", text: item.name }));
    }

    const recipient = item.recipient ? contactName(item.recipient) : null;
    if (recipient) {
      right.appendChild(Global.el("span", { class: "item-badge item-badge-accent", text: recipient }));
    }

    const domain = item.url ? Global.domainFromUrl(item.url) : null;
    if (domain) {
      const domainLink = Global.el("a", {
        class: "item-badge item-badge-domain",
        href: item.url,
        target: "_blank",
        rel: "noopener noreferrer",
        text: domain,
      });
      // Opening the source link shouldn't also toggle the accordion.
      domainLink.addEventListener("click", (e) => e.stopPropagation());
      domainLink.addEventListener("keydown", (e) => e.stopPropagation());
      right.appendChild(domainLink);
    }

    if (item.priority && !item.done) {
      right.appendChild(
        Global.el("span", { class: `item-badge item-badge-priority priority-${item.priority}`, text: ctx.list.priority_labels[item.priority - 1] })
      );
    }

    right.appendChild(Global.el("span", { class: "item-badge item-badge-muted item-badge-progress hidden" }));

    const dateLabel = Global.formatDateBadge(item.needed_by);
    if (dateLabel) {
      right.appendChild(Global.el("span", { class: "item-badge item-badge-date", text: dateLabel }));
    }

    right.appendChild(Global.el("span", { class: "item-chevron", "aria-hidden": "true", text: "▸" }));
  }

  function refreshSummary(card, item, ctx) {
    card.classList.toggle("done", !!item.done);
    renderSummary(card, card.querySelector(":scope > .item-summary"), item, card.querySelector(":scope > .item-details"), ctx);
    applyProgress(card, item, item.progress);
  }

  // Each item is a collapsed-by-default accordion: a single-line summary row
  // (name, recipient, source domain, date) that expands into the full edit
  // form in place - no separate "view" vs "edit" mode, and no modal. This
  // mirrors the jobs admin page (jobs.html/jobs.js) in time-management, which
  // solves the same "lots of rows, only show the full form for the one you're
  // touching" problem the same way.
  function create(item, ctx, { expanded = false } = {}) {
    const card = Global.el("div", {
      class: "item-card" + (expanded ? " expanded" : "") + (item.done ? " done" : ""),
      "data-id": item.id,
    });

    const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });

    // On mouse devices the header isn't itself a button (it holds an editable
    // title); renderSummary makes the right-hand zone the toggle instead.
    const inlineHeader = canInlineEdit();
    const summary = inlineHeader
      ? Global.el("div", { class: "item-summary inline-header" })
      : Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
    renderSummary(card, summary, item, details, ctx);
    if (!inlineHeader) Global.wireAccordionToggle(card, summary, details);

    card.append(summary, details);
    applyProgress(card, item, item.progress);
    details.appendChild(buildItemDetails(card, item, ctx));
    return card;
  }

  // The expanded card has two ways to edit, chosen per device:
  //  - mouse (Global.supportsInlineEdit): each field reads as text, click to
  //    edit, leaving the field saves just that field, Esc cancels. No Save
  //    button.
  //  - touch (and if the shared helper isn't loaded): the classic form - every
  //    field an input, one Save button. Tap-to-edit fights scrolling on a
  //    phone and blur-saves misfire when the keyboard dismisses.
  function buildItemDetails(card, item, ctx) {
    const wrap = Global.el("div", { class: "item-details-inner" });
    const defs = itemFieldDefs(ctx);
    const inline = canInlineEdit();

    // The scrape preview is only shown while the item has a URL, so inline
    // edits of the URL need to be able to rebuild just this part.
    const scrapeHost = Global.el("div");
    function renderScrape() {
      scrapeHost.replaceChildren();
      if (item.url) scrapeHost.appendChild(buildScrapeSection(card, item, ctx));
    }

    // Steps of 10 rather than free entry. Dragging fills the row live ("input"
    // fires continuously); the value is saved on its own when you let go
    // ("change"), so it doesn't need the Save button or re-render the card.
    const progressInput = Global.el("input", { type: "range", min: "0", max: "100", step: "10" });
    progressInput.value = String(item.progress);
    const progressValue = Global.el("span", { class: "progress-value", text: `${item.progress}%` });
    progressInput.addEventListener("input", () => {
      progressValue.textContent = `${progressInput.value}%`;
      applyProgress(card, item, Number(progressInput.value));
    });
    progressInput.addEventListener("change", async () => {
      try {
        const updated = await patchItem(item, { progress: Number(progressInput.value) });
        item.progress = updated.progress;
      } catch (err) {
        progressInput.value = String(item.progress);
        progressValue.textContent = `${item.progress}%`;
        applyProgress(card, item, item.progress);
        Global.showMessage(err.message, "error");
      }
    });

    // Where does the item belong after a save? Returns true if the page
    // reloaded the whole list (so this card is gone or about to be replaced).
    function reloadedAfterSave(updated, name) {
      if (updated.list_id !== ctx.list.id) {
        const target = ctx.lists.find((l) => l.id === updated.list_id);
        Global.showMessage(`Moved "${name}" to ${target ? target.name : "another list"}.`, "success");
        ctx.reload();
        return true;
      }
      return false;
    }

    const fields = Global.el("div", { class: "item-fields" });
    let saveBtn = null;

    if (inline) {
      for (const def of defs) {
        const field = Global.inlineEdit({
          type: def.type,
          value: def.get(item),
          options: def.options,
          required: def.required,
          requiredMessage: def.requiredMessage,
          format: def.format,
          async onSave(raw) {
            const updated = await patchItem(item, { [def.key]: def.toApi(raw) });
            Object.assign(item, updated);
            if (reloadedAfterSave(updated, item.name)) return def.get(updated);
            if (def.key === "priority" && ctx.list.sort_mode === "priority") {
              // Priority decides the order in this mode, so the item may belong elsewhere now.
              ctx.reload();
              return def.get(updated);
            }
            refreshSummary(card, item, ctx);
            if (def.key === "url") renderScrape();
            return def.get(updated);
          },
        });
        fields.appendChild(Global.el("div", { class: "field" }, [Global.el("label", { text: def.label }), field]));
      }
    } else {
      const inputs = Object.fromEntries(defs.map((def) => [def.key, formInput(def, def.get(item))]));
      for (const def of defs) {
        fields.appendChild(Global.el("div", { class: "field" }, [Global.el("label", { text: def.label }), inputs[def.key]]));
      }
      saveBtn = Global.el("button", {
        type: "button",
        class: "save-btn",
        text: "Save",
        onclick: async () => {
          const name = readFormInput(defs[0], inputs.name);
          if (!name) {
            Global.showMessage("Name is required.", "error");
            return;
          }
          try {
            const body = Object.fromEntries(defs.map((def) => [def.key, def.toApi(readFormInput(def, inputs[def.key]))]));
            const updated = await patchItem(item, body);
            if (reloadedAfterSave(updated, name)) return;
            if (updated.priority !== item.priority && ctx.list.sort_mode === "priority") {
              // Priority decides the order in this mode, so the item may belong elsewhere now.
              Global.showMessage(`Saved "${name}".`, "success");
              ctx.reload();
              return;
            }
            Global.showMessage(`Saved "${name}".`, "success");
            card.replaceWith(create(updated, ctx, { expanded: true }));
          } catch (err) {
            Global.showMessage(err.message, "error");
          }
        },
      });
    }

    fields.appendChild(
      Global.el("div", { class: "field" }, [
        Global.el("label", { text: "Progress" }),
        Global.el("div", { class: "progress-control" }, [progressInput, progressValue]),
      ])
    );
    wrap.appendChild(fields);

    renderScrape();
    wrap.appendChild(scrapeHost);

    const actions = Global.el("div", { class: "item-actions" });

    const deleteBtn = Global.el("button", {
      type: "button",
      class: "danger-btn",
      text: "Delete",
      onclick: async () => {
        if (!confirm(`Delete "${item.name}"?`)) return;
        await Global.fetchJSON(`${ITEMS_API}/${item.id}`, { method: "DELETE" });
        card.remove();
        Global.showMessage(`Deleted "${item.name}".`, "success");
        ctx.reload();
      },
    });

    actions.appendChild(deleteBtn);
    if (saveBtn) actions.appendChild(saveBtn);
    wrap.appendChild(actions);
    return wrap;
  }

  function buildScrapeSection(card, item, ctx) {
    const section = Global.el("div", { class: "scrape-section" });

    const scrapeBtn = Global.el("button", {
      type: "button",
      class: "scrape-btn",
      text: item.scrape_status === "not_started" ? "Fetch preview" : "Re-fetch preview",
      onclick: async (e) => {
        e.target.disabled = true;
        e.target.textContent = "Fetching...";
        try {
          const updated = await Global.fetchJSON(`${ITEMS_API}/${item.id}/scrape`, { method: "POST" });
          card.replaceWith(create(updated, ctx, { expanded: true }));
        } catch (err) {
          e.target.disabled = false;
          e.target.textContent = "Fetch preview";
          Global.showMessage(`Preview fetch failed: ${err.message}`, "error");
        }
      },
    });
    section.appendChild(scrapeBtn);
    section.appendChild(renderScrapeStatus(item));
    return section;
  }

  function renderScrapeStatus(item) {
    if (item.scrape_status === "success") {
      const preview = Global.el("div", { class: "scrape-preview" });
      if (item.scraped_image_url) {
        preview.appendChild(Global.el("img", { src: item.scraped_image_url, class: "scrape-image", alt: "" }));
      }
      const textWrap = Global.el("div", { class: "scrape-text" });
      if (item.scraped_title) textWrap.appendChild(Global.el("div", { class: "scrape-title", text: item.scraped_title }));
      if (item.scraped_description) textWrap.appendChild(Global.el("div", { class: "scrape-description", text: item.scraped_description }));
      preview.appendChild(textWrap);
      return preview;
    }
    if (item.scrape_status === "failed") {
      return Global.el("div", { class: "scrape-note scrape-error", text: `Preview fetch failed: ${item.scrape_error || "unknown error"}` });
    }
    if (item.scrape_status === "unsupported") {
      return Global.el("div", { class: "scrape-note", text: "No scraper available for this URL yet." });
    }
    return Global.el("div", { class: "scrape-note", text: "" });
  }

  return { create, contactName };
})();
