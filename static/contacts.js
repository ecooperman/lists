async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = `${url} -> ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (e) {
      // ignore, use default detail
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

function contactDisplayName(contact) {
  return [contact.first_name, contact.last_name].filter(Boolean).join(" ");
}

function contactRowElement(contact) {
  const row = document.createElement("div");
  row.className = "contact-row";
  row.dataset.contactId = contact.id;

  const firstNameInput = document.createElement("input");
  firstNameInput.type = "text";
  firstNameInput.placeholder = "First name";
  firstNameInput.value = contact.first_name;

  const lastNameInput = document.createElement("input");
  lastNameInput.type = "text";
  lastNameInput.placeholder = "Last name";
  lastNameInput.value = contact.last_name || "";

  const emailInput = document.createElement("input");
  emailInput.type = "email";
  emailInput.placeholder = "Email";
  emailInput.value = contact.email || "";

  const addressInput = document.createElement("input");
  addressInput.type = "text";
  addressInput.placeholder = "Address";
  addressInput.value = contact.address || "";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", async () => {
    const firstName = firstNameInput.value.trim();
    if (!firstName) {
      Theme.showMessage("First name is required.", "error");
      return;
    }
    try {
      await fetchJSON(`/api/contacts/${contact.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastNameInput.value.trim() || null,
          email: emailInput.value.trim() || null,
          address: addressInput.value.trim() || null,
        }),
      });
      Theme.showMessage(`Saved "${firstName}".`, "success");
      loadContacts();
    } catch (err) {
      Theme.showMessage(err.message, "error");
    }
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.textContent = "Delete";
  deleteBtn.className = "danger";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete contact "${contactDisplayName(contact)}"?`)) return;
    try {
      await fetchJSON(`/api/contacts/${contact.id}`, { method: "DELETE" });
      Theme.showMessage(`Deleted "${contactDisplayName(contact)}".`, "success");
      loadContacts();
    } catch (err) {
      Theme.showMessage(err.message, "error");
    }
  });

  row.appendChild(firstNameInput);
  row.appendChild(lastNameInput);
  row.appendChild(emailInput);
  row.appendChild(addressInput);
  row.appendChild(saveBtn);
  row.appendChild(deleteBtn);
  return row;
}

async function loadContacts() {
  const contacts = await fetchJSON("/api/contacts");
  const container = document.getElementById("contact-rows");
  container.innerHTML = "";
  for (const contact of contacts) {
    container.appendChild(contactRowElement(contact));
  }
}

function initAddForm() {
  document.getElementById("add-contact-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const firstNameInput = document.getElementById("new-contact-first-name");
    const lastNameInput = document.getElementById("new-contact-last-name");
    const emailInput = document.getElementById("new-contact-email");
    const addressInput = document.getElementById("new-contact-address");
    const firstName = firstNameInput.value.trim();
    if (!firstName) return;
    try {
      await fetchJSON("/api/contacts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastNameInput.value.trim() || null,
          email: emailInput.value.trim() || null,
          address: addressInput.value.trim() || null,
        }),
      });
      firstNameInput.value = "";
      lastNameInput.value = "";
      emailInput.value = "";
      addressInput.value = "";
      Theme.showMessage("Contact added.", "success");
      loadContacts();
    } catch (err) {
      Theme.showMessage(err.message, "error");
    }
  });
}

initAddForm();
loadContacts();
