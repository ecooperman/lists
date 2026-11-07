// "Who has access" for one list: who is on it (with their level, and Remove),
// requests still waiting for the administrator, and a box to add someone by
// email - or, for a person who can't sign in yet, to ask for them to be let in.
// Owners only; the server refuses everyone else.
//
// Used by the list's own page (list.js, inside its Edit form) and by each
// owned list's card on the lists page (lists.js), so both behave identically.
// It builds its own markup (no element ids, so many can be on one page) and
// shows what went wrong right under the box, where the person is looking.
//
//   const access = Access.mount(containerEl, {
//     listId: 3,
//     listName: () => "Gifts",            // read when needed: the name can change
//     onMembers: (members) => { ... },    // after every load, e.g. to update a count
//   });
//   access.reload();                      // refetch (e.g. when its panel opens)

const Access = (() => {
  const ROLE_LABELS = { owner: "Owner", edit: "Can edit", view: "Can view" };

  function mount(container, { listId, listName, onMembers = () => {} }) {
    const api = `/api/lists/${listId}`;
    const send = (url, method, body) =>
      Global.fetchJSON(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });

    const memberList = Global.el("div", { class: "member-list" });
    const inviteList = Global.el("div", { class: "member-list" });

    const emailInput = Global.el("input", {
      type: "email",
      placeholder: "Email address",
      autocomplete: "off",
      "aria-label": "Email address to give access to",
    });
    const roleSelect = Global.el(
      "select",
      { "aria-label": "Access level" },
      ["view", "edit"].map((role) => Global.el("option", { value: role, text: ROLE_LABELS[role] }))
    );
    const addBtn = Global.el("button", { type: "button", class: "secondary-btn", text: "Add" });
    const addRow = Global.el("div", { class: "member-add" }, [emailInput, roleSelect, addBtn]);

    const promptText = Global.el("span");
    const requestBtn = Global.el("button", { type: "button", class: "secondary-btn", text: "Request invite" });
    const prompt = Global.el("div", { class: "invite-prompt hidden" }, [promptText, requestBtn]);

    const hint = Global.el("span", {
      class: "field-hint",
      text:
        "Add someone who already uses the app, or ask for a new person to be let in - an administrator approves each request. " +
        "Viewers can read this list; editors can also change its items. " +
        "Only you can rename it, change who has access, lock it or delete it.",
    });

    container.replaceChildren(memberList, inviteList, addRow, prompt, hint);

    function hidePrompt() {
      prompt.classList.add("hidden");
      prompt.classList.remove("is-error");
    }

    // Say why something didn't go through, right under the box being typed in
    // (the page-wide message sits at the top, out of sight down here).
    function showProblem(text) {
      promptText.textContent = text;
      requestBtn.classList.add("hidden");
      prompt.classList.add("is-error");
      prompt.classList.remove("hidden");
    }

    async function loadMembers() {
      let members;
      try {
        members = await Global.fetchJSON(`${api}/members`);
      } catch (err) {
        showProblem(err.message);
        return;
      }
      onMembers(members);
      memberList.replaceChildren(
        ...members.map((member) => {
          const row = Global.el("div", { class: "member-row" }, [Global.el("span", { class: "member-email", text: member.email })]);
          if (member.role === "owner") {
            row.appendChild(Global.el("span", { class: "item-badge item-badge-muted", text: ROLE_LABELS.owner }));
            return row;
          }
          const select = Global.el(
            "select",
            { "aria-label": `Access for ${member.email}` },
            ["view", "edit"].map((role) => Global.el("option", { value: role, text: ROLE_LABELS[role] }))
          );
          select.value = member.role;
          select.addEventListener("change", async () => {
            try {
              await send(`${api}/members/${member.user_id}`, "PATCH", { role: select.value });
            } catch (err) {
              select.value = member.role;
              showProblem(err.message);
              return;
            }
            member.role = select.value;
          });
          const remove = Global.el("button", { type: "button", class: "cancel-btn", text: "Remove" });
          remove.addEventListener("click", async () => {
            if (!confirm(`Remove ${member.email}'s access to "${listName()}"?`)) return;
            try {
              await send(`${api}/members/${member.user_id}`, "DELETE");
              loadMembers();
            } catch (err) {
              showProblem(err.message);
            }
          });
          row.append(select, remove);
          return row;
        })
      );
    }

    // Requests for people with no account yet: waiting for an administrator, or
    // turned down. (Approved ones are people on the list by then.)
    async function loadInvites() {
      let invites;
      try {
        invites = await Global.fetchJSON(`${api}/invites`);
      } catch (err) {
        showProblem(err.message);
        return;
      }
      inviteList.replaceChildren(
        ...invites.map((invite) => {
          const pending = invite.status === "pending";
          const row = Global.el("div", { class: "member-row" }, [
            Global.el("span", { class: "member-email", text: `${invite.email} - ${ROLE_LABELS[invite.role].toLowerCase()}` }),
            Global.el("span", { class: "item-badge item-badge-muted", text: pending ? "Awaiting approval" : "Declined" }),
          ]);
          if (pending) {
            const withdraw = Global.el("button", { type: "button", class: "cancel-btn", text: "Withdraw" });
            withdraw.addEventListener("click", async () => {
              try {
                await send(`${api}/invites/${invite.id}`, "DELETE");
                loadInvites();
              } catch (err) {
                showProblem(err.message);
              }
            });
            row.appendChild(withdraw);
          }
          return row;
        })
      );
    }

    // The box held someone with no account: say so, and offer to ask for them.
    async function offerInvite() {
      let left = null;
      try {
        left = (await Global.fetchJSON("/api/me")).invites_left;
      } catch (err) {
        // fall through: the server enforces the limit anyway
      }
      const none = left === 0;
      promptText.textContent = none
        ? "That person can't sign in yet, and you've used all your invites."
        : "That person can't sign in yet. You can ask for them to be let in - an administrator has to approve it." +
          (left === null ? "" : ` You have ${left} invite${left === 1 ? "" : "s"} left.`);
      requestBtn.classList.toggle("hidden", none);
      prompt.classList.remove("is-error");
      prompt.classList.remove("hidden");
    }

    async function addPerson() {
      const email = emailInput.value.trim();
      if (!email) return;
      hidePrompt();
      let res;
      try {
        // Raw fetch (not Global.fetchJSON): a 404 here means "no such person
        // yet", which is a prompt rather than an error.
        res = await fetch(`${api}/members`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, role: roleSelect.value }),
        });
      } catch (err) {
        showProblem("Couldn't reach the server - check your connection and try again.");
        return;
      }
      if (res.ok) {
        emailInput.value = "";
        Global.showMessage(`${email} now has access.`, "success");
        loadMembers();
      } else if (res.status === 404) {
        offerInvite();
      } else {
        const body = await res.json().catch(() => ({}));
        showProblem(typeof body.detail === "string" ? body.detail : Global.friendlyStatus(res.status));
      }
    }

    addBtn.addEventListener("click", addPerson);
    requestBtn.addEventListener("click", async () => {
      const email = emailInput.value.trim();
      try {
        const invite = await send(`${api}/invites`, "POST", { email, role: roleSelect.value });
        Global.showMessage(
          invite.status === "approved"
            ? `${invite.email} has been let in and added.`
            : `Requested. ${invite.email} will be added once it's approved.`,
          "success"
        );
      } catch (err) {
        showProblem(err.message);
        return;
      }
      emailInput.value = "";
      hidePrompt();
      loadMembers();
      loadInvites();
    });
    // Changing the address makes the offer about the old one stale.
    emailInput.addEventListener("input", hidePrompt);
    // Enter in the box adds rather than submitting the form around it.
    emailInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addPerson();
      }
    });

    return {
      reload() {
        hidePrompt();
        loadMembers();
        loadInvites();
      },
    };
  }

  return { mount, ROLE_LABELS };
})();
