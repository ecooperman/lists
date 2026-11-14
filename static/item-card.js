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
//   ctx.refreshTotals()  optional: bring the list's cost totals up to date after a
//                 price changed (a list that tracks costs)
//   ctx.canEdit   false for someone with view-only access: the card then shows
//                 the item as plain text, with nothing to edit, check or drag
// They're read when a card is built, so a page can swap in new values by
// reassigning what the getters return.

const ItemCard = (function () {
  const ITEMS_API = "/api/items";
  const LINK_LABELS_API = "/api/link-labels";

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
  // The priority choices this list offers: the levels it has not hidden, plus the one the item
  // already has (a hidden level on an existing item is kept, not silently dropped).
  function priorityOptionsFor(ctx, current) {
    const hidden = ctx.list.hidden_priorities || [];
    const levels = ctx.list.priority_labels
      .map((label, i) => ({ value: String(i + 1), label }))
      .filter((o) => !hidden.includes(Number(o.value)) || Number(o.value) === current);
    return [{ value: "", label: "None" }, ...levels];
  }

  function itemFieldDefs(ctx, item) {
    const contactOptions = [{ value: "", label: "Unassigned" }, ...ctx.contacts.map((c) => ({ value: String(c.id), label: contactName(c) }))];
    const priorityOptions = priorityOptionsFor(ctx, item ? item.priority : null);
    const listOptions = ctx.lists.map((l) => ({ value: String(l.id), label: l.name }));
    return [
      { key: "name", label: "Name", type: "text", required: true, requiredMessage: "Name is required.", get: (it) => it.name, toApi: (v) => v },
      { key: "recipient_id", label: "Who is it for?", type: "select", options: contactOptions, get: (it) => (it.recipient_id ? String(it.recipient_id) : ""), toApi: (v) => (v ? Number(v) : null) },
      { key: "priority", label: "Priority", type: "select", options: priorityOptions, get: (it) => (it.priority ? String(it.priority) : ""), toApi: (v) => (v ? Number(v) : null) },
      { key: "list_id", label: "List", type: "select", options: listOptions, get: (it) => String(it.list_id), toApi: (v) => Number(v) },
      { key: "description", label: "Description", type: "textarea", get: (it) => it.description || "", toApi: (v) => v || null },
      { key: "links", label: "Links", custom: true },
      { key: "needed_by", label: "Needed by", type: "date", format: formatLongDate, get: (it) => Global.toISODate(it.needed_by), toApi: (v) => Global.dateInputToISO(v) },
      ...(ctx.list.track_costs ? costFieldDefs() : []),
    ];
  }

  // The two cost fields of a list that tracks costs. The final cost is optional: left blank,
  // the item counts at its estimate.
  function costFieldDefs() {
    const base = { type: "text", cost: true, format: (v) => formatMoney(parseMoney(v)), toApi: parseMoney };
    return [
      { ...base, key: "estimate_cents", label: "Estimate", placeholder: "Click to add", formPlaceholder: "e.g. 24.99", get: (it) => centsToInput(it.estimate_cents) },
      { ...base, key: "final_cents", label: "Final cost", placeholder: "Same as the estimate", formPlaceholder: "Same as the estimate", get: (it) => centsToInput(it.final_cents) },
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
      if (def.cost) {
        input.setAttribute("inputmode", "decimal");
        input.placeholder = def.formPlaceholder || "";
      }
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

  // "Leave out of the totals" (a list that tracks costs): the item keeps its price but stops counting
  // in any total, so a what-if can be tried and undone with one click. Used by the toggle on the
  // row and the checkbox in the details, which are kept in step here.
  async function setExcluded(card, item, ctx, value) {
    const updated = await patchItem(item, { exclude_from_totals: value });
    Object.assign(item, updated);
    refreshSummary(card, item, ctx);
    const box = card.querySelector(".item-exclude-box");
    if (box) box.checked = !!item.exclude_from_totals;
    if (ctx.refreshTotals) ctx.refreshTotals();
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

    const editable = ctx.canEdit !== false;
    const doneCheckbox = Global.el("input", { type: "checkbox", class: "item-summary-done-toggle", "aria-label": "Mark done" });
    doneCheckbox.checked = !!item.done;
    doneCheckbox.disabled = !editable;
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
    if (!item.done && editable) {
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

    // The first link is the primary one: its site shows on the row (and it is
    // the one a preview is fetched for); "+N" says there are more inside.
    const primary = item.links && item.links.length ? item.links[0] : null;
    const domain = primary ? Global.domainFromUrl(primary.url) : null;
    if (domain) {
      const domainLink = Global.el("a", {
        class: "item-badge item-badge-domain",
        href: primary.url,
        target: "_blank",
        rel: "noopener noreferrer",
        text: domain,
      });
      // Opening the source link shouldn't also toggle the accordion.
      domainLink.addEventListener("click", (e) => e.stopPropagation());
      domainLink.addEventListener("keydown", (e) => e.stopPropagation());
      right.appendChild(domainLink);
      if (item.links.length > 1) {
        right.appendChild(
          Global.el("span", {
            class: "item-badge item-badge-muted item-badge-more-links",
            title: `${item.links.length} links`,
            text: `+${item.links.length - 1}`,
          })
        );
      }
    }

    if (item.priority && !item.done) {
      right.appendChild(
        Global.el("span", { class: `item-badge item-badge-priority priority-${item.priority}`, text: ctx.list.priority_labels[item.priority - 1] })
      );
    }

    if (ctx.list.track_costs && item.cost_cents !== null && item.cost_cents !== undefined) {
      const final = item.final_cents !== null && item.final_cents !== undefined;
      const left = item.exclude_from_totals;
      right.appendChild(
        Global.el("span", {
          class: "item-badge item-badge-muted item-badge-cost" + (left ? " item-badge-excluded" : ""),
          title: (final ? `Final cost${item.estimate_cents != null ? ` (estimated ${formatMoney(item.estimate_cents)})` : ""}` : "Estimate") + (left ? " - left out of the totals" : ""),
          text: formatMoney(item.cost_cents),
        })
      );
    }
    if (ctx.list.track_costs && editable && (item.exclude_from_totals || (item.cost_cents !== null && item.cost_cents !== undefined))) {
      const left = !!item.exclude_from_totals;
      const toggle = Global.el("span", {
        class: "item-exclude-toggle" + (left ? " on" : ""),
        role: "button",
        tabindex: "0",
        "aria-pressed": String(left),
        "aria-label": left ? "Count this item in the totals again" : "Leave this item out of the totals",
        title: left ? "Left out of the totals - click to count it again" : "Leave out of the totals",
      }, [Global.el("span", { class: "btn-icon", "data-icon": left ? "eye-off" : "eye", "aria-hidden": "true" })]);
      applyIcons(toggle);
      const flip = async () => {
        try {
          await setExcluded(card, item, ctx, !left);
        } catch (err) {
          Global.showMessage(err.message, "error");
        }
      };
      toggle.addEventListener("click", (e) => {
        e.stopPropagation(); // must not also expand or collapse the card
        flip();
      });
      toggle.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          flip();
        }
      });
      right.appendChild(toggle);
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
    card.classList.toggle("excluded", !!item.exclude_from_totals);
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
      class: "item-card" + (expanded ? " expanded" : "") + (item.done ? " done" : "") + (item.exclude_from_totals ? " excluded" : ""),
      "data-id": item.id,
    });

    const details = Global.el("div", { class: "item-details" + (expanded ? "" : " hidden") });

    // On mouse devices the header isn't itself a button (it holds an editable
    // title); renderSummary makes the right-hand zone the toggle instead.
    const editable = ctx.canEdit !== false;
    const inlineHeader = editable && canInlineEdit();
    const summary = inlineHeader
      ? Global.el("div", { class: "item-summary inline-header" })
      : Global.el("button", { type: "button", class: "item-summary", "aria-expanded": String(expanded) });
    renderSummary(card, summary, item, details, ctx);
    if (!inlineHeader) Global.wireAccordionToggle(card, summary, details);

    card.append(summary, details);
    applyProgress(card, item, item.progress);
    details.appendChild(editable ? buildItemDetails(card, item, ctx) : buildReadonlyDetails(item, ctx));
    return card;
  }

  // What someone with view-only access sees when they expand an item: the
  // fields that have something in them, as plain text.
  function buildReadonlyDetails(item, ctx) {
    const wrap = Global.el("div", { class: "item-details-inner" });
    const fields = Global.el("div", { class: "item-fields" });
    const add = (label, value) => {
      if (value === null || value === undefined || value === "") return;
      fields.appendChild(Global.el("div", { class: "field" }, [Global.el("label", { text: label }), value]));
    };
    const text = (value) => Global.el("div", { class: "readonly-value", text: value });

    add("Who is it for?", item.recipient ? text(contactName(item.recipient)) : null);
    add("Priority", item.priority ? text(ctx.list.priority_labels[item.priority - 1]) : null);
    add("Description", item.description ? text(item.description) : null);
    for (const link of item.links || []) {
      add(
        link.label || "Link",
        Global.el("a", { class: "readonly-value", href: link.url, target: "_blank", rel: "noopener noreferrer", text: link.url })
      );
    }
    add("Needed by", item.needed_by ? text(formatLongDate(Global.toISODate(item.needed_by))) : null);
    if (ctx.list.track_costs) {
      add("Estimate", item.estimate_cents != null ? text(formatMoney(item.estimate_cents)) : null);
      add("Final cost", item.final_cents != null ? text(formatMoney(item.final_cents)) : null);
    }
    add("Progress", item.progress ? text(`${item.progress}%`) : null);
    if (!fields.children.length) fields.appendChild(Global.el("p", { class: "preview-empty", text: "No more details." }));
    wrap.appendChild(fields);
    if (item.links && item.links.length) wrap.appendChild(Global.el("div", { class: "item-actions" }, [copyLinksButton(item)]));
    if (item.scrape_status === "success") wrap.appendChild(Global.el("div", { class: "scrape-section" }, [renderScrapeStatus(item)]));
    return wrap;
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
    const defs = itemFieldDefs(ctx, item);
    const inline = canInlineEdit();

    // The scrape preview is only shown while the item has a URL, so inline
    // edits of the URL need to be able to rebuild just this part.
    const scrapeHost = Global.el("div");
    function renderScrape() {
      scrapeHost.replaceChildren();
      if (item.links && item.links.length) scrapeHost.appendChild(buildScrapeSection(card, item, ctx));
    }

    // The links save themselves, like progress (see buildLinksEditor), one
    // after another through this queue.
    // One click copies the item's name and links for pasting to someone.
    const copyBtn = copyLinksButton(item);
    const linksQueue = createSaveQueue();
    const linksEditor = buildLinksEditor(item, {
      queue: linksQueue,
      inline,
      onSaved() {
        refreshSummary(card, item, ctx);
        renderScrape();
        copyBtn.classList.toggle("hidden", !item.links.length);
      },
    });

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
        if (def.custom) {
          fields.appendChild(Global.el("div", { class: "field field-links" }, [Global.el("label", { text: def.label }), linksEditor]));
          continue;
        }
        const field = Global.inlineEdit({
          type: def.type,
          value: def.get(item),
          options: def.options,
          required: def.required,
          requiredMessage: def.requiredMessage,
          format: def.format,
          placeholder: def.placeholder,
          async onSave(raw) {
            const updated = await patchItem(item, { [def.key]: def.toApi(raw) });
            Object.assign(item, updated);
            if (reloadedAfterSave(updated, item.name)) return def.get(updated);
            if (def.key === "priority" && ctx.list.sort_mode === "priority") {
              // Priority decides the order in this mode, so the item may belong elsewhere now.
              ctx.reload();
              return def.get(updated);
            }
            if (def.cost) {
              // A price changes the list's totals (and the order, when sorted by price).
              if (ctx.list.sort_mode === "price") {
                ctx.reload();
                return def.get(updated);
              }
              if (ctx.refreshTotals) ctx.refreshTotals();
            } else if (def.key === "priority" && ctx.refreshTotals) {
              ctx.refreshTotals(); // the by-priority lines of the totals strip move with it
            }
            refreshSummary(card, item, ctx);
            return def.get(updated);
          },
        });
        fields.appendChild(Global.el("div", { class: "field" }, [Global.el("label", { text: def.label }), field]));
      }
    } else {
      const fieldDefs = defs.filter((def) => !def.custom);
      const inputs = Object.fromEntries(fieldDefs.map((def) => [def.key, formInput(def, def.get(item))]));
      for (const def of defs) {
        const control = def.custom ? linksEditor : inputs[def.key];
        fields.appendChild(Global.el("div", { class: def.custom ? "field field-links" : "field" }, [Global.el("label", { text: def.label }), control]));
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
            // A link being edited saves itself as you leave its field; let
            // that finish first so the card isn't rebuilt from older data.
            await linksQueue.settled();
            const body = Object.fromEntries(fieldDefs.map((def) => [def.key, def.toApi(readFormInput(def, inputs[def.key]))]));
            const updated = await patchItem(item, body);
            if (reloadedAfterSave(updated, name)) return;
            if (updated.priority !== item.priority && ctx.list.sort_mode === "priority") {
              // Priority decides the order in this mode, so the item may belong elsewhere now.
              Global.showMessage(`Saved "${name}".`, "success");
              ctx.reload();
              return;
            }
            Global.showMessage(`Saved "${name}".`, "success");
            if (ctx.list.sort_mode === "price") {
              ctx.reload();
              return;
            }
            card.replaceWith(create(updated, ctx, { expanded: true }));
            if (ctx.refreshTotals) ctx.refreshTotals();
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
    if (ctx.list.track_costs && ctx.canEdit !== false) {
      const box = Global.el("input", { type: "checkbox", class: "item-exclude-box", "aria-label": "Leave out of the totals" });
      box.checked = !!item.exclude_from_totals;
      box.addEventListener("change", async () => {
        try {
          await setExcluded(card, item, ctx, box.checked);
        } catch (err) {
          box.checked = !box.checked;
          Global.showMessage(err.message, "error");
        }
      });
      fields.appendChild(
        Global.el("div", { class: "field checkbox-field field-exclude" }, [
          box,
          Global.el("label", { text: "Leave out of the totals - keeps the price on the list but does not count it, handy for a what-if" }),
        ])
      );
    }
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
    actions.appendChild(copyBtn);
    if (saveBtn) actions.appendChild(saveBtn);
    wrap.appendChild(actions);
    return wrap;
  }

  // The "Copy links" button on an item (hidden while it has none): copies the
  // item's name and links to the clipboard (send-copy.js), view-only members too.
  function copyLinksButton(item) {
    const button = Global.el("button", { type: "button", class: "secondary-btn item-copy-links", text: "Copy links" });
    button.classList.toggle("hidden", !(item.links && item.links.length));
    button.addEventListener("click", () => SendCopy.copyItemLinks(item, button));
    return button;
  }

  // --- links ---
  //
  // An item has any number of links, each an address plus an optional label
  // saying what it is. The label is picked from the person's own list of link
  // labels (the Link Labels page) so it can't be mistyped, and "Add new
  // label..." in the dropdown adds one to that list on the spot. The first
  // link is the primary one (previewed, and shown on the collapsed row); drag
  // the handle to change which that is.

  let linkLabels = [];
  let linkLabelsLoading = null;

  // The person's own label names, in their order. Pages call this once before
  // building cards; a failure just leaves the dropdown with fewer choices.
  function loadLinkLabels() {
    if (!linkLabelsLoading) {
      linkLabelsLoading = Global.fetchJSON(LINK_LABELS_API)
        .then((labels) => {
          linkLabels = labels.map((l) => l.name);
        })
        .catch((err) => console.error("Failed to load link labels", err));
    }
    return linkLabelsLoading;
  }

  // Runs saves one at a time, in order, so a quick second edit can't be
  // overtaken by the first; settled() waits for whatever is in flight.
  function createSaveQueue() {
    let tail = Promise.resolve();
    return {
      run(task) {
        const result = tail.then(task);
        tail = result.catch(() => {});
        return result;
      },
      settled() {
        return tail;
      },
    };
  }

  const WEB_ADDRESS = /^https?:\/\/\S+$/i;
  const ADD_LABEL = "__add__";

  // The choices for one link's label: no label, then the person's labels, then
  // the link's own current label if it isn't one of them (a collaborator's
  // wording, or one since deleted) so it doesn't silently vanish on edit, then
  // the way to make a new one.
  function labelOptions(current) {
    const names = current && !linkLabels.includes(current) ? [...linkLabels, current] : linkLabels;
    return [
      { value: "", label: "No label" },
      ...names.map((name) => ({ value: name, label: name })),
      { value: ADD_LABEL, label: "Add new label..." },
    ];
  }

  // The same choices for an ordinary <select> (touch devices).
  function fillLabelOptions(select, current) {
    select.replaceChildren(...labelOptions(current).map((o) => Global.el("option", { value: o.value, text: o.label })));
    select.value = current || "";
  }

  // Adds a label to the person's own list; a name they already have (any
  // capitalisation) is reused rather than refused. Resolves with the name to
  // use, or null if it couldn't be added (the error is shown).
  async function addLabel(name) {
    const existing = linkLabels.find((n) => n.toLowerCase() === name.toLowerCase());
    if (existing) return existing;
    try {
      const created = await Global.fetchJSON(LINK_LABELS_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      linkLabels.push(created.name);
      return created.name;
    } catch (err) {
      Global.showMessage(err.message, "error");
      return null;
    }
  }

  // Swaps `anchor` (the label control) for a small "name it" form until it is
  // answered; done(name) gets the label to use, or null if it was cancelled.
  // (The form itself is shared-assets' Global.askForName.)
  function askForLabel(anchor, done) {
    Global.askForName(
      anchor,
      { placeholder: "New label", formClass: "link-new-label-form", inputClass: "link-new-label", cancelClass: "link-cancel", submit: addLabel },
      done
    );
  }

  // The links field. On a mouse, each label and address reads as plain text
  // and is edited by clicking it, like the item's other fields; on touch they
  // are ordinary inputs (see buildItemDetails for why). Either way a change is
  // saved as soon as it is made: the whole set of links is sent, in order.
  // Each row keeps its own values in `row._link`, so what is saved never
  // depends on which kind of control is showing.
  function buildLinksEditor(item, { queue, inline, onSaved }) {
    const wrap = Global.el("div", { class: "links-editor" });
    const rows = Global.el("div", { class: "link-rows" });
    const refreshers = []; // redraw every row's label choices after one is added
    const signatureOf = (links) => JSON.stringify(links.map((l) => [l.label || null, l.url]));
    let saved = signatureOf(item.links || []);

    // What the rows hold now, in order. A row with no address yet is just a
    // place to type, not a link.
    function collect() {
      return [...rows.querySelectorAll(":scope > .link-row")]
        .map((row) => ({ label: row._link.label || null, url: row._link.url.trim() }))
        .filter((l) => l.url);
    }

    // Saves what the rows hold; throws (for the caller to show) if it can't.
    async function save() {
      const links = collect();
      if (links.some((l) => !WEB_ADDRESS.test(l.url))) {
        throw new Error("A link must be a web address starting with http:// or https://");
      }
      if (signatureOf(links) === saved) return;
      await queue.run(async () => {
        const updated = await patchItem(item, { links });
        item.links = updated.links;
        item.url = updated.url;
        // A different primary link voids the preview fetched for the old one.
        item.scrape_status = updated.scrape_status;
        item.scraped_title = updated.scraped_title;
        item.scraped_description = updated.scraped_description;
        item.scraped_image_url = updated.scraped_image_url;
        item.scrape_error = updated.scrape_error;
        saved = signatureOf(updated.links);
        onSaved();
      });
    }

    async function saveAndShowErrors() {
      try {
        await save();
      } catch (err) {
        Global.showMessage(err.message, "error");
      }
    }

    function rowElement(link) {
      const row = Global.el("div", { class: "link-row" });
      row._link = { label: link.label || "", url: link.url || "" };
      const handle = Global.el("span", { class: "link-drag-handle", "aria-label": "Drag to reorder", text: "⋮⋮" });
      const removeBtn = Global.el("button", { type: "button", class: "link-remove", "aria-label": "Remove link", "data-btn-icon": "x", text: "×" });

      // Change one field and save; if that fails the field goes back to what it was.
      async function change(field, value) {
        const previous = row._link[field];
        row._link[field] = value;
        try {
          await save();
        } catch (err) {
          row._link[field] = previous;
          throw err;
        }
      }

      if (inline) {
        const options = [];
        const refresh = () => options.splice(0, options.length, ...labelOptions(row._link.label));
        refresh();
        refreshers.push(refresh);
        const labelField = Global.inlineEdit({
          type: "select",
          value: row._link.label,
          options,
          placeholder: "No label",
          className: "link-label-edit",
          async onSave(raw) {
            if (raw === ADD_LABEL) {
              askForLabel(labelField, async (name) => {
                if (!name) return;
                refreshers.forEach((fn) => fn());
                try {
                  await change("label", name);
                  labelField.setValue(name);
                } catch (err) {
                  Global.showMessage(err.message, "error");
                }
              });
              return row._link.label;
            }
            await change("label", raw);
            refresh();
            return raw;
          },
        });
        const openLink = Global.el("a", { class: "link-open", target: "_blank", rel: "noopener noreferrer", title: "Open this link", "aria-label": "Open this link" }, [
          Global.el("span", { class: "btn-icon", "data-icon": "external", "aria-hidden": "true" }),
        ]);
        applyIcons(openLink);
        const showOpen = () => {
          if (row._link.url) openLink.setAttribute("href", row._link.url);
          else openLink.removeAttribute("href");
          openLink.classList.toggle("hidden", !row._link.url);
        };
        showOpen();
        const urlField = Global.inlineEdit({
          type: "url",
          value: row._link.url,
          placeholder: "Click to add a link",
          className: "link-url-edit",
          async onSave(raw) {
            if (!WEB_ADDRESS.test(raw)) throw new Error("A link must be a web address starting with http:// or https://");
            await change("url", raw);
            showOpen();
            return raw;
          },
        });
        row._focusUrl = () => urlField.querySelector(".inline-edit-display").click();
        row.append(handle, labelField, urlField, openLink, removeBtn);
      } else {
        const select = Global.el("select", { class: "link-label", "aria-label": "What this link is" });
        fillLabelOptions(select, row._link.label);
        refreshers.push(() => fillLabelOptions(select, row._link.label));
        const urlInput = Global.el("input", { type: "url", class: "link-url", placeholder: "https://...", maxlength: "2000", "aria-label": "Link address" });
        urlInput.value = row._link.url;
        select.addEventListener("change", () => {
          if (select.value !== ADD_LABEL) {
            row._link.label = select.value;
            saveAndShowErrors();
            return;
          }
          askForLabel(select, async (name) => {
            if (!name) {
              select.value = row._link.label;
              return;
            }
            refreshers.forEach((fn) => fn());
            row._link.label = name;
            select.value = name;
            await saveAndShowErrors();
          });
        });
        urlInput.addEventListener("change", () => {
          row._link.url = urlInput.value.trim();
          saveAndShowErrors();
        });
        urlInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            urlInput.blur();
          }
        });
        row._focusUrl = () => urlInput.focus();
        row.append(handle, select, urlInput, removeBtn);
      }

      removeBtn.addEventListener("click", async () => {
        const next = row.nextSibling;
        row.remove();
        try {
          await save();
        } catch (err) {
          rows.insertBefore(row, next);
          Global.showMessage(err.message, "error");
        }
      });
      return row;
    }

    for (const link of item.links || []) rows.appendChild(rowElement(link));

    const addBtn = Global.el("button", {
      type: "button",
      class: "link-add",
      "data-btn-icon": "plus",
      text: "+ Add link",
      onclick: () => {
        const row = rowElement({ label: "", url: "" });
        rows.appendChild(row);
        row._focusUrl();
      },
    });

    if (typeof Sortable !== "undefined") {
      Sortable.create(rows, {
        handle: ".link-drag-handle",
        draggable: ".link-row",
        animation: 150,
        forceFallback: true,
        onEnd(evt) {
          if (evt.oldIndex !== evt.newIndex) saveAndShowErrors();
        },
      });
    }

    wrap.append(rows, addBtn);
    return wrap;
  }

  function buildScrapeSection(card, item, ctx) {
    const section = Global.el("div", { class: "scrape-section" });

    const scrapeBtn = Global.el("button", {
      type: "button",
      class: "scrape-btn",
      "data-btn-icon": "refresh",
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

  return { create, contactName, loadLinkLabels };
})();
