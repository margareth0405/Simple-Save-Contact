# ContactHub — Phase 1 Frontend

ContactHub is a responsive contact management frontend for the ITP16 Final Requirement. This phase demonstrates contact CRUD, search, category filtering, dashboard statistics, form validation, and confirmation dialogs entirely in the browser.

> **Demo data only:** Phase 1 uses browser `localStorage` as temporary demonstration storage. It is not the final database. Use only fictional contact details while testing.

## Technology

- HTML5
- CSS3
- Bootstrap 5.3
- Vanilla JavaScript
- Browser `localStorage` (temporary Phase 1 storage)

No Flask backend, SQLite database, Gunicorn, Nginx, or AWS resources are included in this phase.

## Preview locally

The quickest option is to double-click `index.html`. It redirects to the static dashboard preview.

For a more realistic local web-server preview, open PowerShell in the `contacthub` folder and run:

```powershell
python -m http.server 8000
```

Then open <http://localhost:8000> in a browser. An internet connection is needed to load Bootstrap from its CDN.

## Features to test

1. Open the dashboard and confirm the total and today's contact counts.
2. Select **Manage Contacts** or the **Contacts** navigation link.
3. Search by name, email, or phone number.
4. Filter contacts by Family, Friends, Work, or Others.
5. Add a fictional contact and verify form validation.
6. Edit an existing contact and confirm that its current values appear in the form.
7. Delete a contact using the confirmation modal.
8. Refresh the page and confirm the changes remain in the same browser.
9. Select **Restore sample contacts** to reset the demo dataset.

## Project structure

```text
contacthub/
├── index.html                  # Static preview entry point
├── templates/
│   ├── base.html               # Flask/Jinja base layout scaffold for Phase 2
│   ├── dashboard.html          # Standalone Phase 1 dashboard preview
│   └── contacts.html           # Standalone Phase 1 contact manager
├── static/
│   ├── css/style.css           # Responsive visual system
│   └── js/app.js               # Demo CRUD, validation, search, filter, and stats
└── README.md
```

`dashboard.html` and `contacts.html` are intentionally standalone so Phase 1 can be previewed without Flask. `base.html` establishes the future Jinja layout. In Phase 2, the two page templates will extend `base.html` to remove repeated navigation and footer markup.

## Phase 2 integration plan

The existing form fields and contact object map directly to an SQLite `contacts` table: `id`, `full_name`, `email`, `phone`, `category`, `address`, `notes`, and `date_added`.

The Flask integration will:

- Add routes for the dashboard, contact list, create, update, delete, search, and filter operations.
- Replace `readContacts()` and `writeContacts()` in `app.js` with Flask-rendered data or `fetch()` requests to JSON endpoints.
- Perform all validation again on the server, even though browser validation remains for usability.
- Store records in SQLite and generate IDs in the database/service layer.
- Use Jinja template inheritance through `base.html` and Flask `url_for()` paths.
- Add CSRF protection, database error handling, and automated CRUD tests.

Phase 3 deployment to EC2 should begin only after the Flask/SQLite implementation and tests are complete.
