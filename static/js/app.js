(function () {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const isAdmin = document.body.dataset.isAdmin === "true";
  const loginUrl = document.body.dataset.loginUrl;
  let currentContacts = [];
  let pendingDeleteId = null;
  let listRequestNumber = 0;
  let searchTimer = null;

  async function apiRequest(url, options = {}) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.body) headers["Content-Type"] = "application/json";
    if (options.method && options.method !== "GET") {
      headers["X-CSRF-Token"] = document.querySelector('meta[name="csrf-token"]').content;
    }
    const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(data?.error || `Request failed (${response.status}).`);
      error.fields = data?.fields || {};
      error.status = response.status;
      if (response.status === 401) window.location.assign(loginUrl);
      throw error;
    }
    return data;
  }

  function formatDate(dateValue) {
    const date = new Date(dateValue);
    if (Number.isNaN(date.getTime())) return "Unknown";
    return new Intl.DateTimeFormat("en-PH", { year: "numeric", month: "short", day: "numeric" }).format(date);
  }

  function initials(name) {
    return name.trim().split(/\s+/).slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join("") || "?";
  }

  function createCell(value, className) {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = value;
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

  async function renderDashboard() {
    if (document.body.dataset.page !== "dashboard") return;
    try {
      const data = await apiRequest("/api/dashboard/stats");
      byId("totalContacts").textContent = String(data.total);
      byId("todayContacts").textContent = String(data.addedToday);
      const categories = byId("categoryStats");
      categories.replaceChildren();
      data.categoryCounts.forEach((category) => {
        const column = document.createElement("div");
        column.className = "col-6 col-lg-3";
        const card = document.createElement("div");
        card.className = "stat-card h-100";
        const content = document.createElement("div");
        const label = document.createElement("p");
        label.className = "stat-label";
        label.textContent = category.name;
        const count = document.createElement("p");
        count.className = "stat-value mb-0";
        count.textContent = String(category.count);
        content.append(label, count);
        card.appendChild(content);
        column.appendChild(card);
        categories.appendChild(column);
      });
      const body = byId("recentContactsBody");
      body.replaceChildren();
      data.recent.forEach((contact) => {
        const row = document.createElement("tr");
        const personCell = document.createElement("td");
        personCell.appendChild(createPerson(contact, true));
        const categoryCell = document.createElement("td");
        categoryCell.appendChild(createCategory(contact.category));
        row.append(personCell, createCell(contact.phone), categoryCell, createCell(formatDate(contact.addedAt)));
        body.appendChild(row);
      });
      const isEmpty = data.recent.length === 0;
      body.closest(".table-responsive").classList.toggle("d-none", isEmpty);
      byId("recentEmpty").classList.toggle("d-none", !isEmpty);
    } catch (error) {
      showToast(`Could not load dashboard: ${error.message}`, "error");
    }
  }

  function createActionCell(contact) {
    const cell = document.createElement("td");
    cell.className = "text-end";
    if (!isAdmin) {
      const link = document.createElement("a");
      link.href = document.body.dataset.manageLoginUrl;
      link.className = "stat-link";
      link.textContent = "Sign in to manage";
      cell.appendChild(link);
      return cell;
    }
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

  async function renderContacts() {
    if (document.body.dataset.page !== "contacts") return;
    const requestNumber = ++listRequestNumber;
    const search = byId("contactSearch").value.trim();
    const category = byId("categoryFilter").value;
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (category) params.set("category", category);
    try {
      const data = await apiRequest(`/api/contacts${params.size ? `?${params}` : ""}`);
      if (requestNumber !== listRequestNumber) return;
      currentContacts = data.contacts;
      const body = byId("contactsTableBody");
      body.replaceChildren();
      currentContacts.forEach((contact) => {
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

      const noResults = currentContacts.length === 0;
      byId("contactsTableWrap").classList.toggle("d-none", noResults);
      byId("contactsEmpty").classList.toggle("d-none", !noResults);
      const filtering = Boolean(search || category);
      byId("emptyTitle").textContent = filtering ? "No matching contacts" : "No contacts available";
      byId("emptyMessage").textContent = filtering ? "Try changing your search or category filter." : "Add a fictional contact to begin building your directory.";
      byId("emptyAddButton").classList.toggle("d-none", filtering);
      byId("resultsSummary").textContent = filtering
        ? `Showing ${currentContacts.length} of ${data.total} contacts`
        : `Showing ${currentContacts.length} ${currentContacts.length === 1 ? "contact" : "contacts"}`;
    } catch (error) {
      if (requestNumber === listRequestNumber) showToast(`Could not load contacts: ${error.message}`, "error");
    }
  }

  function bootstrapModal(id) {
    if (!window.bootstrap) {
      showToast("Bootstrap did not load. Connect to the internet and refresh the page.", "error");
      return null;
    }
    return window.bootstrap.Modal.getOrCreateInstance(byId(id));
  }

  function clearFormErrors() {
    const form = byId("contactForm");
    form.classList.remove("was-validated");
    form.querySelectorAll(".is-invalid").forEach((field) => field.classList.remove("is-invalid"));
    form.querySelectorAll("input, select, textarea").forEach((field) => field.setCustomValidity(""));
    byId("formError").classList.add("d-none");
  }

  function openContactForm(contact) {
    if (!isAdmin) {
      window.location.assign(loginUrl);
      return;
    }
    const form = byId("contactForm");
    form.reset();
    clearFormErrors();
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
    if (!/^[+() 0-9-]+$/.test(value)) return false;
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

  function displayFormError(error) {
    const fieldMessages = Object.entries(error.fields || {});
    fieldMessages.forEach(([field, message]) => {
      const input = byId(field);
      if (input) {
        input.classList.add("is-invalid");
        input.setCustomValidity(message);
      }
    });
    const alert = byId("formError");
    alert.textContent = fieldMessages.length
      ? `${error.message} ${fieldMessages.map(([field, message]) => `${field}: ${message}`).join(" ")}`
      : error.message;
    alert.classList.remove("d-none");
    alert.focus();
  }

  async function saveContact(event) {
    event.preventDefault();
    clearFormErrors();
    if (!validateForm()) {
      displayFormError(new Error("Please correct the highlighted fields before saving."));
      return;
    }

    const id = byId("contactId").value;
    const contact = {
      fullName: byId("fullName").value.trim(),
      email: byId("email").value.trim(),
      phone: byId("phone").value.trim(),
      category: byId("category").value,
      address: byId("address").value.trim(),
      notes: byId("notes").value.trim()
    };
    const saveButton = byId("saveContactButton");
    saveButton.disabled = true;
    try {
      await apiRequest(id ? `/api/contacts/${encodeURIComponent(id)}` : "/api/contacts", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(contact)
      });
      bootstrapModal("contactModal")?.hide();
      await renderContacts();
      showToast(id ? "Contact updated successfully." : "Contact added successfully.", "success");
    } catch (error) {
      displayFormError(error);
    } finally {
      saveButton.disabled = false;
    }
  }

  function openDelete(contact) {
    pendingDeleteId = contact.id;
    byId("deleteContactName").textContent = contact.fullName;
    bootstrapModal("deleteModal")?.show();
  }

  async function confirmDelete() {
    if (!pendingDeleteId) return;
    const id = pendingDeleteId;
    const contact = currentContacts.find((item) => item.id === id);
    const button = byId("confirmDeleteButton");
    button.disabled = true;
    try {
      await apiRequest(`/api/contacts/${encodeURIComponent(id)}`, { method: "DELETE" });
      pendingDeleteId = null;
      bootstrapModal("deleteModal")?.hide();
      await renderContacts();
      showToast(contact ? `${contact.fullName} was deleted.` : "Contact deleted.", "success");
    } catch (error) {
      showToast(`Could not delete contact: ${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
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

  async function loadCategories() {
    try {
      const data = await apiRequest("/api/categories");
      for (const [id, label] of [["categoryFilter", "All categories"], ["category", "Choose a category"]]) {
        const select = byId(id);
        const placeholder = new Option(label, "");
        select.replaceChildren(placeholder);
        data.categories.forEach((category) => select.add(new Option(category.name, category.name)));
      }
    } catch (error) {
      showToast(`Could not load categories: ${error.message}`, "error");
    }
  }

  async function initializeContactsPage() {
    if (document.body.dataset.page !== "contacts") return;
    byId("addContactButton").addEventListener("click", () => openContactForm(null));
    byId("emptyAddButton").addEventListener("click", () => openContactForm(null));
    byId("contactSearch").addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(renderContacts, 200);
    });
    byId("categoryFilter").addEventListener("change", renderContacts);
    byId("contactForm").addEventListener("submit", saveContact);
    byId("contactForm").addEventListener("input", (event) => {
      if (event.target.matches("input, select, textarea")) {
        event.target.setCustomValidity("");
        event.target.classList.remove("is-invalid");
      }
    });
    byId("notes").addEventListener("input", updateNotesCount);
    byId("confirmDeleteButton").addEventListener("click", confirmDelete);
    byId("contactsTableBody").addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const id = button.dataset.contactId;
      if (button.dataset.action === "edit") {
        try {
          const data = await apiRequest(`/api/contacts/${encodeURIComponent(id)}`);
          openContactForm(data.contact);
        } catch (error) {
          showToast(`Could not load contact: ${error.message}`, "error");
        }
      }
      if (button.dataset.action === "delete") {
        const contact = currentContacts.find((item) => item.id === id);
        if (contact) openDelete(contact);
      }
    });
    byId("deleteModal").addEventListener("hidden.bs.modal", () => { pendingDeleteId = null; });
    await loadCategories();
    await renderContacts();
    if (new URLSearchParams(window.location.search).get("action") === "add") openContactForm(null);
  }

  document.addEventListener("DOMContentLoaded", () => {
    renderDashboard();
    initializeContactsPage();
  });
})();
