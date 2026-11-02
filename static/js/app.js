(function () {
  "use strict";

  const STORAGE_KEY = "contacthub_demo_contacts_v1";
  const CATEGORIES = ["Family", "Friends", "Work", "Others"];
  let memoryContacts = [];
  let storageAvailable = true;
  let pendingDeleteId = null;

  const byId = (id) => document.getElementById(id);

  function localDate(daysAgo) {
    const date = new Date();
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() - daysAgo);
    return date.toISOString();
  }

  function sampleContacts() {
    return [
      { id: "CH-1001", fullName: "Mia Santos", email: "mia.santos@example.com", phone: "+63 917 555 0101", category: "Friends", address: "Quezon City", notes: "Fictional sample contact.", addedAt: localDate(0) },
      { id: "CH-1002", fullName: "Noah Reyes", email: "noah.reyes@example.com", phone: "+63 918 555 0102", category: "Work", address: "Makati City", notes: "Fictional project teammate.", addedAt: localDate(0) },
      { id: "CH-1003", fullName: "Ava Mendoza", email: "ava.mendoza@example.com", phone: "+63 919 555 0103", category: "Family", address: "Pasig City", notes: "Fictional sample contact.", addedAt: localDate(1) },
      { id: "CH-1004", fullName: "Liam Garcia", email: "liam.garcia@example.com", phone: "+63 920 555 0104", category: "Others", address: "Manila", notes: "Fictional community contact.", addedAt: localDate(3) },
      { id: "CH-1005", fullName: "Sofia Cruz", email: "sofia.cruz@example.com", phone: "+63 921 555 0105", category: "Work", address: "Taguig City", notes: "Fictional professional contact.", addedAt: localDate(5) }
    ];
  }

  function readContacts() {
    if (!storageAvailable) return [...memoryContacts];
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        const seeded = sampleContacts();
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(seeded));
        return seeded;
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) throw new Error("Saved contact data is invalid.");
      return parsed.filter(isContactShape);
    } catch (error) {
      storageAvailable = false;
      memoryContacts = sampleContacts();
      updateStorageNotice();
      return [...memoryContacts];
    }
  }

  function writeContacts(contacts) {
    memoryContacts = [...contacts];
    if (!storageAvailable) return true;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(contacts));
      return true;
    } catch (error) {
      storageAvailable = false;
      updateStorageNotice();
      showToast("Browser storage is unavailable. Changes will last only until this page is refreshed.", "error");
      return true;
    }
  }

  function isContactShape(contact) {
    return contact && typeof contact.id === "string" && typeof contact.fullName === "string" &&
      typeof contact.email === "string" && typeof contact.phone === "string" &&
      CATEGORIES.includes(contact.category) && typeof contact.addedAt === "string";
  }

  function updateStorageNotice() {
    const notice = byId("storageNotice");
    if (!notice || storageAvailable) return;
    const text = notice.querySelector("div");
    if (text) text.textContent = "Browser storage is unavailable. ContactHub is using temporary in-memory demo data for this tab only.";
  }

  function todayKey(dateValue) {
    const date = dateValue ? new Date(dateValue) : new Date();
    if (Number.isNaN(date.getTime())) return "";
    return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("-");
  }

  function formatDate(dateValue) {
    const date = new Date(dateValue);
    if (Number.isNaN(date.getTime())) return "Unknown";
    return new Intl.DateTimeFormat("en-PH", { year: "numeric", month: "short", day: "numeric" }).format(date);
  }

  function initials(name) {
    return name.trim().split(/\s+/).slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join("") || "?";
  }

  function createCell(text, className) {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = text;
    return cell;
  }

  function createPerson(contact, includeEmail) {
    const wrapper = document.createElement("div");
    wrapper.className = "contact-person";
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = initials(contact.fullName);
    const text = document.createElement("div");
    const name = document.createElement("span");
    name.className = "person-name";
    name.textContent = contact.fullName;
    text.appendChild(name);
    if (includeEmail) {
      const email = document.createElement("span");
      email.className = "person-email";
      email.textContent = contact.email;
      text.appendChild(email);
    }
    wrapper.append(avatar, text);
    return wrapper;
  }

  function createCategory(category) {
    const badge = document.createElement("span");
    badge.className = `category-badge category-${category.toLowerCase()}`;
    badge.textContent = category;
    return badge;
  }

  function renderDashboard() {
    if (document.body.dataset.page !== "dashboard") return;
    const contacts = readContacts().sort((a, b) => new Date(b.addedAt) - new Date(a.addedAt));
    byId("totalContacts").textContent = String(contacts.length);
    const today = todayKey();
    byId("todayContacts").textContent = String(contacts.filter((contact) => todayKey(contact.addedAt) === today).length);

    const body = byId("recentContactsBody");
    const empty = byId("recentEmpty");
    body.replaceChildren();
    contacts.slice(0, 5).forEach((contact) => {
      const row = document.createElement("tr");
      const personCell = document.createElement("td");
      personCell.appendChild(createPerson(contact, true));
      const categoryCell = document.createElement("td");
      categoryCell.appendChild(createCategory(contact.category));
      row.append(personCell, createCell(contact.phone), categoryCell, createCell(formatDate(contact.addedAt)));
      body.appendChild(row);
    });
    const isEmpty = contacts.length === 0;
    body.closest(".table-responsive").classList.toggle("d-none", isEmpty);
    empty.classList.toggle("d-none", !isEmpty);
  }

  function filteredContacts() {
    const query = (byId("contactSearch")?.value || "").trim().toLocaleLowerCase();
    const category = byId("categoryFilter")?.value || "";
    return readContacts()
      .filter((contact) => !category || contact.category === category)
      .filter((contact) => !query || [contact.fullName, contact.email, contact.phone].some((value) => value.toLocaleLowerCase().includes(query)))
      .sort((a, b) => new Date(b.addedAt) - new Date(a.addedAt));
  }

  function renderContacts() {
    if (document.body.dataset.page !== "contacts") return;
    const contacts = filteredContacts();
    const allContacts = readContacts();
    const body = byId("contactsTableBody");
    const tableWrap = byId("contactsTableWrap");
    const empty = byId("contactsEmpty");
    body.replaceChildren();

    contacts.forEach((contact) => {
      const row = document.createElement("tr");
      row.appendChild(createCell(contact.id, "contact-id"));
      const personCell = document.createElement("td");
      personCell.appendChild(createPerson(contact, false));
      row.appendChild(personCell);
      row.appendChild(createCell(contact.email));
      row.appendChild(createCell(contact.phone));
      const categoryCell = document.createElement("td");
      categoryCell.appendChild(createCategory(contact.category));
      row.appendChild(categoryCell);
      row.appendChild(createCell(formatDate(contact.addedAt)));
      row.appendChild(createActionCell(contact));
      body.appendChild(row);
    });

    const noResults = contacts.length === 0;
    tableWrap.classList.toggle("d-none", noResults);
    empty.classList.toggle("d-none", !noResults);
    const filtering = Boolean(byId("contactSearch").value.trim() || byId("categoryFilter").value);
    byId("emptyTitle").textContent = filtering ? "No matching contacts" : "No contacts available";
    byId("emptyMessage").textContent = filtering ? "Try changing your search or category filter." : "Add a fictional contact to begin building your directory.";
    byId("emptyAddButton").classList.toggle("d-none", filtering);
    byId("resultsSummary").textContent = filtering ? `Showing ${contacts.length} of ${allContacts.length} contacts` : `Showing ${contacts.length} ${contacts.length === 1 ? "contact" : "contacts"}`;
  }

  function createActionCell(contact) {
    const cell = document.createElement("td");
    cell.className = "text-end";
    const group = document.createElement("div");
    group.className = "action-group";
    group.append(
      actionButton("Edit", "btn-outline-primary", "edit", contact.id),
      actionButton("Delete", "btn-outline-danger", "delete", contact.id)
    );
    cell.appendChild(group);
    return cell;
  }

  function actionButton(label, buttonClass, action, id) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `btn ${buttonClass} table-action`;
    button.dataset.action = action;
    button.dataset.contactId = id;
    button.setAttribute("aria-label", `${label} contact ${id}`);
    button.textContent = label;
    return button;
  }

  function bootstrapModal(id) {
    if (!window.bootstrap) {
      showToast("Bootstrap did not load. Connect to the internet and refresh the page.", "error");
      return null;
    }
    return window.bootstrap.Modal.getOrCreateInstance(byId(id));
  }

  function openContactForm(contact) {
    const form = byId("contactForm");
    form.reset();
    form.classList.remove("was-validated");
    byId("formError").classList.add("d-none");
    const editing = Boolean(contact);
    byId("contactModalKicker").textContent = editing ? "UPDATE CONTACT" : "NEW CONTACT";
    byId("contactModalTitle").textContent = editing ? "Edit Contact" : "Add Contact";
    byId("saveContactButton").textContent = editing ? "Save Changes" : "Save Contact";
    byId("contactId").value = contact?.id || "";
    byId("fullName").value = contact?.fullName || "";
    byId("email").value = contact?.email || "";
    byId("phone").value = contact?.phone || "";
    byId("category").value = contact?.category || "";
    byId("address").value = contact?.address || "";
    byId("notes").value = contact?.notes || "";
    updateNotesCount();
    bootstrapModal("contactModal")?.show();
  }

  function validPhone(value) {
    if (!/^[+()\-\s\d]+$/.test(value)) return false;
    const digits = value.replace(/\D/g, "");
    return digits.length >= 7 && digits.length <= 15;
  }

  function validateForm() {
    const form = byId("contactForm");
    const name = byId("fullName");
    const phone = byId("phone");
    name.setCustomValidity(name.value.trim().length >= 2 ? "" : "Name is too short.");
    phone.setCustomValidity(validPhone(phone.value.trim()) ? "" : "Invalid phone number.");
    form.classList.add("was-validated");
    return form.checkValidity();
  }

  function generateId(contacts) {
    const used = new Set(contacts.map((contact) => contact.id));
    const highest = contacts.reduce((max, contact) => {
      const match = /^CH-(\d+)$/.exec(contact.id);
      return match ? Math.max(max, Number(match[1])) : max;
    }, 1000);
    let number = highest + 1;
    while (used.has(`CH-${number}`)) number += 1;
    return `CH-${number}`;
  }

  function saveContact(event) {
    event.preventDefault();
    if (!validateForm()) {
      const error = byId("formError");
      error.textContent = "Please correct the highlighted fields before saving.";
      error.classList.remove("d-none");
      error.focus();
      return;
    }

    const contacts = readContacts();
    const id = byId("contactId").value;
    const existingIndex = contacts.findIndex((contact) => contact.id === id);
    const contact = {
      id: existingIndex >= 0 ? id : generateId(contacts),
      fullName: byId("fullName").value.trim(),
      email: byId("email").value.trim(),
      phone: byId("phone").value.trim(),
      category: byId("category").value,
      address: byId("address").value.trim(),
      notes: byId("notes").value.trim(),
      addedAt: existingIndex >= 0 ? contacts[existingIndex].addedAt : new Date().toISOString()
    };

    if (existingIndex >= 0) contacts[existingIndex] = contact;
    else contacts.push(contact);
    writeContacts(contacts);
    bootstrapModal("contactModal")?.hide();
    renderContacts();
    showToast(existingIndex >= 0 ? "Contact updated successfully." : "Contact added successfully.", "success");
  }

  function openDelete(contact) {
    pendingDeleteId = contact.id;
    byId("deleteContactName").textContent = contact.fullName;
    bootstrapModal("deleteModal")?.show();
  }

  function confirmDelete() {
    if (!pendingDeleteId) return;
    const contacts = readContacts();
    const contact = contacts.find((item) => item.id === pendingDeleteId);
    writeContacts(contacts.filter((item) => item.id !== pendingDeleteId));
    pendingDeleteId = null;
    bootstrapModal("deleteModal")?.hide();
    renderContacts();
    showToast(contact ? `${contact.fullName} was deleted.` : "Contact deleted.", "success");
  }

  function showToast(message, type) {
    const region = byId("toastRegion");
    if (!region) return;
    const toast = document.createElement("div");
    toast.className = `toast show toast-${type || "success"}`;
    toast.setAttribute("role", type === "error" ? "alert" : "status");
    toast.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
    toast.setAttribute("aria-atomic", "true");
    const body = document.createElement("div");
    body.className = "toast-body d-flex align-items-center justify-content-between gap-3";
    const text = document.createElement("span");
    text.textContent = message;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "btn-close";
    close.setAttribute("aria-label", "Dismiss notification");
    close.addEventListener("click", () => toast.remove());
    body.append(text, close);
    toast.appendChild(body);
    region.appendChild(toast);
    window.setTimeout(() => toast.remove(), 4500);
  }

  function updateNotesCount() {
    const notes = byId("notes");
    const count = byId("notesCount");
    if (notes && count) count.textContent = String(notes.value.length);
  }

  function restoreSamples() {
    writeContacts(sampleContacts());
    byId("contactSearch").value = "";
    byId("categoryFilter").value = "";
    renderContacts();
    showToast("Fictional sample contacts restored.", "success");
  }

  function initializeContactsPage() {
    if (document.body.dataset.page !== "contacts") return;
    byId("addContactButton").addEventListener("click", () => openContactForm(null));
    byId("emptyAddButton").addEventListener("click", () => openContactForm(null));
    byId("contactSearch").addEventListener("input", renderContacts);
    byId("categoryFilter").addEventListener("change", renderContacts);
    byId("resetDemoButton").addEventListener("click", restoreSamples);
    byId("contactForm").addEventListener("submit", saveContact);
    byId("notes").addEventListener("input", updateNotesCount);
    byId("confirmDeleteButton").addEventListener("click", confirmDelete);
    byId("contactsTableBody").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const contact = readContacts().find((item) => item.id === button.dataset.contactId);
      if (!contact) {
        showToast("That contact could not be found. Refresh and try again.", "error");
        return;
      }
      if (button.dataset.action === "edit") openContactForm(contact);
      if (button.dataset.action === "delete") openDelete(contact);
    });
    byId("deleteModal").addEventListener("hidden.bs.modal", () => { pendingDeleteId = null; });
    renderContacts();
    if (new URLSearchParams(window.location.search).get("action") === "add") openContactForm(null);
  }

  document.addEventListener("DOMContentLoaded", () => {
    readContacts();
    updateStorageNotice();
    renderDashboard();
    initializeContactsPage();
  });
})();
