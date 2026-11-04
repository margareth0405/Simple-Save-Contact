# ContactHub — ITP16 Contact Management System

ContactHub uses the existing Bootstrap 5 interface with Flask and a relational SQLite database. Visitors can view, search, and filter fictional contacts. An administrator signs in to add, edit, or delete them. This is the completed Phase 2 implementation; AWS deployment is reserved for Phase 3.

## Objectives and design

- Demonstrate Create, Read, Update, and Delete operations through a responsive website.
- Store contacts in `contacthub.db` outside the public `static/` directory.
- Keep category names in a separate `categories` table and enforce `contacts.category_id → categories.id` with `ON DELETE RESTRICT`.
- Validate requests on the server, protect writes with administrator sign-in and CSRF checks, and keep passwords and Flask session secrets out of tracked source files.
- Provide a repeatable local setup and a path to later Ubuntu EC2 deployment.

The existing dashboard, contact table, form modals, confirmation dialog, navigation, and `style.css` remain in place. Browser `localStorage` is not used for contact records.

## Windows 11 setup in PowerShell

Run these commands in a new PowerShell window. The first path is the project's current location; adjust it if you move the folder again.

```powershell
Set-Location -LiteralPath 'C:\Users\Ja Ja\Desktop\ITP_16\ITP16_Testing\contacthub'
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python setup_database.py
python insert_sample_data.py
python setup_admin.py
python -m flask --app app run
```

`setup_admin.py` asks you to choose and confirm a password of at least 12 characters for username `admin`. It stores a password hash and a stable random session secret in the ignored `instance/admin_config.json`. It does not print or save the plaintext password. Run it again to change the password; the session secret stays the same. Restart Flask after changing the password.

The database is `instance/contacthub.db` by default. On this upgraded local copy, the first `setup_database.py` run copied the five existing fictional contacts from `instance/contacthub.sqlite3` into the new relational schema and left the old file untouched. Repeating setup does not duplicate categories or reimport deleted contacts. `insert_sample_data.py` inserts only missing fictional sample records and is never run automatically by the web app.

Open <http://127.0.0.1:5000/>. Open **Contacts** to browse. Select **Admin sign in**, enter username `admin` and your chosen password, then use the existing Add, Edit, and Delete controls. An internet connection is needed for the Bootstrap CDN assets.

### Verify CRUD and persistence

1. Sign in and add a fictional contact. Confirm it appears in the table and increases the dashboard total and category count.
2. Search by its name, email, or phone, then filter by its category.
3. Edit it and confirm the form opens with the saved values. Save and refresh to confirm the change remains.
4. Delete it using the confirmation dialog; check that the total and category count decrease.
5. Stop Flask with `Ctrl+C`, start it again with `python -m flask --app app run`, and verify the remaining records are still present.
6. Sign out and confirm the list remains readable while write actions require sign-in.

## Database schema and API

| Table | Key fields | Relationship |
| --- | --- | --- |
| `categories` | `id` primary key, unique `name` | Family, Friends, Work, Others |
| `contacts` | `id` primary key, name, email, phone, address, notes, creation and update times | `category_id` references `categories.id` with delete restriction |

All application connections enable SQLite foreign keys. Queries use parameters for user input. SQLite allocates unique integer keys; the interface displays them as `CH-1001`, `CH-1002`, and so on. Times are stored in UTC, and the dashboard's "added today" count uses `CONTACTHUB_TIME_ZONE` (default `Asia/Manila`).

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Dashboard page |
| `GET` | `/contacts` | Contact manager page |
| `GET`, `POST` | `/login` | Administrator sign-in |
| `POST` | `/logout` | Sign out |
| `GET` | `/api/categories` | Available categories |
| `GET` | `/api/contacts` | List; optional `search` and `category` parameters |
| `GET` | `/api/contacts/<id>` | Retrieve one contact |
| `POST` | `/api/contacts` | Create; administrator only |
| `PUT` | `/api/contacts/<id>` | Update; administrator only |
| `DELETE` | `/api/contacts/<id>` | Delete; administrator only |
| `GET` | `/api/dashboard/stats` | Totals, today's count, recent contacts, and counts by category |

The previous `/api/stats` URL remains as a compatibility alias. Write requests require a signed-in session and the CSRF token from the page. Validation errors return HTTP 422 with field messages; unauthorized writes return HTTP 401.

## Inspect `contacthub.db`

Open `instance/contacthub.db` with [DB Browser for SQLite](https://sqlitebrowser.org/) and use **Database Structure** to view `categories` and `contacts`, or **Browse Data** to see saved rows. In **Execute SQL**, these read-only queries show keys and relationships:

```sql
PRAGMA table_info(categories);
PRAGMA table_info(contacts);
PRAGMA foreign_key_list(contacts);
SELECT contacts.id, contacts.full_name, contacts.email, categories.name AS category,
       contacts.created_at, contacts.updated_at
FROM contacts JOIN categories ON categories.id = contacts.category_id
ORDER BY contacts.id;
```

You can also use a VS Code SQLite extension that can open a local `.db` file and run SQL, then execute the same queries. Close the inspection tool before manually moving or restoring the database. Avoid editing the database directly while Flask is writing to it.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The 22 automated tests use disposable SQLite files. They cover schema creation, foreign keys and restricted category deletion, legacy migration, repeatable seeding, password hashing, login and logout, CSRF, complete contact CRUD, duplicate submissions, malformed requests, database failures, validation, search, category filtering, dashboard statistics, and persistence across a new Flask app instance. They do not modify `instance/contacthub.db`.

## Troubleshooting

- `ModuleNotFoundError: flask`: activate `.venv`, then run `python -m pip install -r requirements.txt`.
- PowerShell blocks activation: run `Set-ExecutionPolicy -Scope Process Bypass`, then activate `.venv` again. This changes only the current PowerShell process.
- `no such table: contacts`: run `python setup_database.py` from the project directory and confirm `CONTACTHUB_DATABASE` points to the intended file.
- Login says administrator is not configured: run `python setup_admin.py`, then restart Flask.
- HTTP 401 on a write: sign in as administrator. HTTP 403: refresh the page to get a new CSRF token, then try again.
- `database is locked`: close DB inspection tools or other writers and retry. Do not copy a live WAL database by copying only its main `.db` file.
- Styling or modals do not load: check internet access to the Bootstrap CDN. Flask must be running; opening a template directly will not work.

## Configuration and EC2 preparation

`CONTACTHUB_DATABASE` accepts an absolute path or one relative to this project, allowing a persistent Ubuntu path such as `/var/lib/contacthub/contacthub.db`. `CONTACTHUB_ADMIN_CONFIG` likewise points to the private administrator config file. `CONTACTHUB_TIME_ZONE` defaults to `Asia/Manila`. For EC2, the supplied Gunicorn, systemd, and Nginx examples are in `deploy/`, with a runbook in [DEPLOY_EC2.md](DEPLOY_EC2.md). No AWS resources were created.

On Ubuntu, new SQLite and administrator config files are created with mode `0600`. Keep their parent directory restricted to the service account. Use persistent EBS storage and back up the database; see the deployment guide. Public visitors can read the contacts, so use fictional information until HTTPS and the desired privacy restrictions are configured.

## Documentation evidence for the ITP16 report

Capture your own screenshots of the dashboard, category counts, contact list, validation error, add/edit/delete flow, administrator login, database structure, and test result. Record the exact Windows and later EC2 configuration used, your setup procedure, any troubleshooting steps, and a conclusion about CRUD and persistence. Screenshots and EC2 results must come from your own run; they are not included or claimed here.

## Project structure

```text
contacthub/
  app.py                 Flask routes, authentication, validation, and API
  database.py            Reusable SQLite connection
  schema.sql             Relational database schema
  setup_database.py      Repeatable schema setup and one-time legacy import
  insert_sample_data.py  Explicit fictional sample insertion
  setup_admin.py         Interactive administrator password setup
  requirements.txt       Python dependencies
  instance/              Ignored database and administrator config
  templates/             Existing pages plus login.html
  static/                Existing CSS and JavaScript
  tests/                 Temporary-database automated tests
  deploy/                Future EC2 service and Nginx examples
  DEPLOY_EC2.md          Future deployment runbook
```

## Conclusion

Phase 2 now demonstrates a relational SQLite database, authenticated writes, working contact CRUD, search, filtering, and live dashboard statistics through the preserved frontend. Local tests and server checks establish the development behavior; public EC2 deployment remains a separate Phase 3 task.
