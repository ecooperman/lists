// "Send a copy": a one-time snapshot of a list (or one item's links) that
// goes to the clipboard, for pasting into a message, note or email. Not the
// same as sharing access (see TODO.md, "Words we use for sharing"). Anyone who
// can see a list can do it. The wording of the copy is made by the server
// (app/sendcopy.py) so an emailed copy can later match it exactly; this file is
// the chooser, the preview and the clipboard. Needs Global from theme.js.

const SendCopy = (function () {
  const DEFAULTS = {
    links: true,
    description: false,
    needed_by: false,
    priority: false,
    progress: false,
    recipient: false,
    prices: false,
    style: "bulleted",
    done: "show",
    order: "list",
    heading: true,
  };

  const INCLUDE = [
    ["links", "Links"],
    ["description", "Description"],
    ["needed_by", "Needed by"],
    ["priority", "Priority"],
    ["progress", "Progress"],
    ["recipient", "Who it's for"],
    ["prices", "Prices and total"],
    ["heading", "List name as a heading"],
  ];

  const SELECTS = [
    ["style", "Layout", [["bulleted", "Bulleted"], ["numbered", "Numbered"], ["checkboxes", "Checkboxes"], ["plain", "Plain lines"]]],
    ["done", "Done items", [["show", "Show"], ["hide", "Leave out"], ["strike", "Mark as done"]]],
    ["order", "Order", [["list", "As on the list"], ["priority", "By priority"]]],
  ];

  // What was chosen last time for a list is remembered on this device only.
  function storageKey(listId) {
    return `lists.sendCopy.${listId}`;
  }

  function loadChoices(listId) {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey(listId)) || "{}");
      return { ...DEFAULTS, ...saved };
    } catch (err) {
      return { ...DEFAULTS };
    }
  }

  function saveChoices(listId, choices) {
    try {
      localStorage.setItem(storageKey(listId), JSON.stringify(choices));
    } catch (err) {
      // Private windows and blocked storage just forget; nothing depends on it.
    }
  }

  function post(url, options) {
    return Global.fetchJSON(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });
  }

  // Puts the text and the rich version on the clipboard. Takes a promise of
  // {text, html}: browsers only allow a clipboard write inside the click that
  // asked for it, and handing over the pending result keeps that true while
  // the copy is still being fetched. Resolves with the result.
  async function writeClipboard(resultPromise) {
    if (navigator.clipboard && window.ClipboardItem) {
      const blob = (key, type) => resultPromise.then((r) => new Blob([r[key]], { type }));
      try {
        await navigator.clipboard.write([
          new ClipboardItem({ "text/plain": blob("text", "text/plain"), "text/html": blob("html", "text/html") }),
        ]);
        return await resultPromise;
      } catch (err) {
        // Fall through: plain text still works where the rich write doesn't.
      }
    }
    const result = await resultPromise; // throws here if fetching it was what failed
    if (!navigator.clipboard) throw new Error("Your browser won't let this page copy. Try the preview text instead.");
    await navigator.clipboard.writeText(result.text);
    return result;
  }

  // One click on an item: its name and links, ready to paste.
  async function copyItemLinks(item, button) {
    const original = button ? button.textContent : "";
    try {
      await writeClipboard(post(`/api/items/${item.id}/copy`, { style: "plain", heading: false, links: true }));
      Global.showMessage(`Copied "${item.name}" and its links.`, "success");
      if (button) {
        button.textContent = "Copied";
        setTimeout(() => (button.textContent = original), 1500);
      }
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  }

  // The chooser for a whole list, built into `container`. Returns
  // { refresh() } - call it each time the panel is opened, since the list may
  // have changed since. onClose, if given, adds a Close button.
  function mount(container, { listId, onClose, tracksCosts = () => false }) {
    const choices = loadChoices(listId);
    const options = Global.el("div", { class: "send-copy-options" });
    const inputs = {};

    let pricesRow = null;
    const include = Global.el("fieldset", { class: "send-copy-include" }, [Global.el("legend", { text: "Include" })]);
    for (const [key, label] of INCLUDE) {
      const box = Global.el("input", { type: "checkbox" });
      box.checked = !!choices[key];
      inputs[key] = box;
      const row = Global.el("label", { class: "send-copy-check" }, [box, ` ${label}`]);
      if (key === "prices") pricesRow = row; // only offered on a list that tracks costs
      include.appendChild(row);
    }
    options.appendChild(include);

    const choose = Global.el("div", { class: "send-copy-choose" });
    for (const [key, label, values] of SELECTS) {
      const select = Global.el("select", {}, values.map(([value, text]) => Global.el("option", { value, text })));
      select.value = choices[key];
      inputs[key] = select;
      choose.appendChild(Global.el("div", { class: "field" }, [Global.el("label", { text: label }), select]));
    }
    options.appendChild(choose);

    const preview = Global.el("pre", { class: "send-copy-preview", "aria-live": "polite" });
    const note = Global.el("span", { class: "field-hint", text: "Messages and notes get the plain text above. Email and documents get a version where link labels are clickable." });
    const copyBtn = Global.el("button", { type: "button", class: "save-btn", text: "Copy" });
    // Feedback sits beside the button: the page's message bar is at the top of
    // the page and is out of sight when the panel is scrolled into view.
    const status = Global.el("span", { class: "send-copy-status", role: "status" });
    const actions = Global.el("div", { class: "item-actions" }, [copyBtn, status]);
    if (onClose) actions.appendChild(Global.el("button", { type: "button", class: "cancel-btn", text: "Close", onclick: onClose }));

    // Emailing the same copy: one address, sent from the app on the person's
    // behalf with replies coming to them. The server makes the email from the
    // chosen options itself, so what arrives is what the preview shows (plus a
    // short note at the end saying who it is from).
    const emailInput = Global.el("input", { type: "email", placeholder: "friend@example.com", autocomplete: "off", "aria-label": "Email address to send the copy to" });
    const emailBtn = Global.el("button", { type: "button", class: "save-btn", text: "Email it" });
    const emailStatus = Global.el("span", { class: "send-copy-status", role: "status" });
    const emailHint = Global.el("span", {
      class: "field-hint",
      text: "Sent from Lists on your behalf; replies come to you. A short note at the end says who it is from and that it is a one-time copy.",
    });
    const emailBox = Global.el("div", { class: "field send-copy-email" }, [
      Global.el("label", { text: "Or email it to" }),
      Global.el("div", { class: "send-copy-email-row" }, [emailInput, emailBtn]),
      emailStatus,
      emailHint,
    ]);

    container.replaceChildren(options, preview, note, actions, emailBox);

    function current() {
      const now = {};
      for (const key of Object.keys(DEFAULTS)) {
        const input = inputs[key];
        now[key] = input.type === "checkbox" ? input.checked : input.value;
      }
      if (!tracksCosts()) now.prices = false;
      return now;
    }

    let result = null;
    let version = 0;
    async function refresh() {
      pricesRow.classList.toggle("hidden", !tracksCosts());
      const now = current();
      saveChoices(listId, now);
      const mine = ++version;
      copyBtn.disabled = true;
      try {
        const fetched = await post(`/api/lists/${listId}/copy`, now);
        if (mine !== version) return; // a newer choice is already on its way
        result = fetched;
        preview.textContent = fetched.text;
        copyBtn.disabled = false;
      } catch (err) {
        if (mine === version) Global.showMessage(err.message, "error");
      }
    }

    for (const input of Object.values(inputs)) input.addEventListener("change", refresh);

    copyBtn.addEventListener("click", async () => {
      if (!result) return;
      const shown = result;
      status.className = "send-copy-status";
      status.textContent = "";
      try {
        await writeClipboard(Promise.resolve(shown));
        status.textContent = `Copied ${shown.count} item${shown.count === 1 ? "" : "s"} to the clipboard.`;
        copyBtn.textContent = "Copied";
        setTimeout(() => {
          copyBtn.textContent = "Copy";
          status.textContent = "";
        }, 3000);
      } catch (err) {
        status.className = "send-copy-status send-copy-status-error";
        status.textContent = err.message || "Couldn't copy.";
      }
    });

    async function sendEmail() {
      const to = emailInput.value.trim();
      emailStatus.className = "send-copy-status";
      emailStatus.textContent = "";
      if (!to) {
        emailStatus.className = "send-copy-status send-copy-status-error";
        emailStatus.textContent = "Type the email address to send it to.";
        emailInput.focus();
        return;
      }
      emailBtn.disabled = true;
      emailBtn.textContent = "Sending...";
      try {
        const sent = await post(`/api/lists/${listId}/email`, { ...current(), to });
        const left = sent.left_today == null ? "" : ` ${sent.left_today} more ${sent.left_today === 1 ? "email" : "emails"} left today.`;
        emailStatus.textContent = `Sent to ${sent.sent_to}.${left}`;
        emailInput.value = "";
      } catch (err) {
        emailStatus.className = "send-copy-status send-copy-status-error";
        emailStatus.textContent = err.message || "Couldn't send it.";
      } finally {
        emailBtn.disabled = false;
        emailBtn.textContent = "Email it";
      }
    }

    emailBtn.addEventListener("click", sendEmail);
    emailInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendEmail();
      }
    });

    return { refresh };
  }

  return { mount, copyItemLinks };
})();
