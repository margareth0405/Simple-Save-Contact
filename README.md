# ContactHub — Flask and SQLite

ContactHub is a responsive contact management system for the ITP16 Final Requirement. The existing Bootstrap 5 dashboard and contact manager now use a Flask JSON API backed by SQLite. Contacts remain available after browser refreshes and are shared by visitors to the same server.

**Use fictional contacts for this school demonstration.** The project does not yet have user accounts or per-user access control. Anyone who can reach a publicly deployed instance can view and change its contacts. Add authentication and HTTPS before using real personal information.

## Local setup

From the `contacthub` directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m flask --app app init-db
python -m flask --app app seed-demo
python -m flask --app app run
```

Open <http://127.0.0.1:5000/>. `seed-demo` is optional; it inserts five fictional sample contacts only when the table is empty. Do not double-click a template or use `python -m http.server`: Flask now renders the pages and handles all data requests. An internet connection is needed for the Bootstrap CDN assets.

The local SQLite file is `instance/contacthub.sqlite3` by default. Set `CONTACTHUB_DATABASE` to an absolute path to use a different file. The database and local environment files are ignored by Git.

## Features

- Dashboard totals, today's additions, and five newest contacts from SQLite
- Contact creation, listing, editing, and deletion with confirmation
- Search by name, email, or phone, plus category filtering
- Browser and server-side validation with field-specific errors
- Unique `CH-1001` style display IDs generated from SQLite primary keys
- CSRF checks for create, update, and delete requests
- Responsive Bootstrap layout and safe text rendering

## Test

```powershell
python -m unittest discover -s tests -v
```

The tests use separate temporary SQLite files and cover CRUD, persistence, search/filtering, validation failures, unique IDs, CSRF, templates, and optional demo seeding. They do not modify the local preview database.

## Structure

```text
contacthub/
├── app.py                       Flask app, validation, routes, and CLI commands
├── schema.sql                   SQLite table and indexes
├── requirements.txt             Python dependencies
├── .env.example                 EC2 service environment template
├── templates/
│   ├── base.html                Shared Jinja layout
│   ├── dashboard.html           Dashboard page
│   └── contacts.html            Contact manager and modals
├── static/
│   ├── css/style.css            Responsive styling
│   └── js/app.js                API calls and page interactions
├── tests/test_app.py            Flask and SQLite integration tests
├── deploy/                      systemd and Nginx example configurations
├── DEPLOY_EC2.md                Ubuntu EC2 runbook
└── README.md
```

## API and database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/stats` | Dashboard counts and recent contacts |
| `GET` | `/api/contacts` | List contacts; optional `search` and `category` query parameters |
| `GET` | `/api/contacts/<id>` | Get one contact for editing |
| `POST` | `/api/contacts` | Create a contact |
| `PUT` | `/api/contacts/<id>` | Update a contact |
| `DELETE` | `/api/contacts/<id>` | Delete a contact |

Write requests send JSON and the `X-CSRF-Token` header from the rendered page. The schema stores an integer primary key, full name, email, phone, category, optional address and notes, and the UTC creation timestamp. Public display IDs are derived from the integer key; SQLite `AUTOINCREMENT` prevents reuse after deletion. The dashboard's "added today" count uses `CONTACTHUB_TIME_ZONE` (default `Asia/Manila`).

## EC2 readiness

The project includes a Gunicorn systemd unit, an Nginx reverse proxy configuration, a private environment-file template, and step-by-step instructions in [DEPLOY_EC2.md](DEPLOY_EC2.md). AWS deployment has not been performed or verified from this workspace.
