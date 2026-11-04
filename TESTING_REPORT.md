# ContactHub Phase 2 verification report

Date: 5 November 2026 (Asia/Manila)  
Scope: Local Windows Flask application and existing `instance/contacthub.db`. No AWS resources were created.

## Testing objectives and method

Verify the actual database schema and integrity, exercise CRUD and security behavior through Flask's request client with disposable SQLite files, confirm the local server starts and serves the expected pages and assets, and identify remaining EC2 deployment gates. The existing database was opened for read-only inspection. All automated write tests used temporary databases.

## A. Application status

| Component | Expected result | Actual result | Status |
| --- | --- | --- | --- |
| Flask entry point | `app:app` imports and starts | Local Flask server started with debug off | PASS |
| Dashboard, contacts, login | Pages return successful responses | All three returned HTTP 200 over local HTTP | PASS |
| CSS and JavaScript | Assets are served | Both returned HTTP 200; `node --check` passed | PASS |
| Browser interaction and responsive layout | Forms, modals, navigation, mobile layout, and console work in a real browser | Browser-control session unavailable; no visual or console run was made | UNTESTED |
| SQLite connection | App uses one configured database outside `static/` | Absolute path resolved to `instance/contacthub.db`; app connection reported `PRAGMA foreign_keys = 1` | PASS |

The older `instance/contacthub.sqlite3` is an intentional preserved legacy file. `contacthub.sqbpro` is an existing DB Browser project file, not another application database; it was left untouched.

## B. CRUD and feature results

| Test case | Expected result | Actual result | Status |
| --- | --- | --- | --- |
| Create | POST saves a fictional contact to SQLite | HTTP 201; row and unique `CH-` display ID verified in temporary SQLite file | PASS |
| Read | GET returns saved record and category name | List and detail JSON matched database row; local app listed 5 existing records | PASS |
| Update | PUT saves changes and update timestamp | HTTP 200; category relationship and `updatedAt` changed while `addedAt` remained stable | PASS |
| Delete | DELETE removes record permanently | HTTP 204; subsequent GET returned 404 and list count decreased | PASS |
| Persistence | Refresh/restart retains current records | New Flask app instance read the same temporary SQLite record | PASS (request-level) |
| Search and filter | Name, email, phone, and category queries return matching rows | Automated queries passed; local search for a fictional contact returned one row | PASS (API) |
| Dashboard statistics | Total, today, recent, and per-category values reflect SQLite | Automated assertions passed; local total was 5 and category counts summed to 5 | PASS (API) |
| Empty database | Empty list and zero counts are handled | Automated list/total behavior passed; visual empty-state rendering not exercised | PARTIAL |
| Add/edit/delete UI, success/error messages | Modal flows and notifications work in browser | Relevant JavaScript and templates inspected; no browser interaction run | UNTESTED |

## C. Database integrity

Read-only checks on the existing `instance/contacthub.db`:

| Check | Actual result | Status |
| --- | --- | --- |
| File exists | Yes; absolute path configured outside `static/` | PASS |
| `PRAGMA integrity_check` | `ok` | PASS |
| `PRAGMA foreign_key_check` | No violation rows | PASS |
| `PRAGMA table_info(contacts)` | 9 columns; `id` primary key, required name/email/phone/category ID and timestamps | PASS |
| `PRAGMA table_info(categories)` | `id` primary key and required name | PASS |
| `PRAGMA foreign_key_list(contacts)` | `category_id` references `categories.id`, `ON DELETE RESTRICT` | PASS |
| Existing rows | 5 contacts and 4 categories; records retrievable | PASS |
| Foreign-key enforcement | Shared application connection returned `1`; invalid references and restricted category deletion failed in tests | PASS |
| Connections closed | Flask teardown and script `closing(...)` verified in code; temporary-file tests completed on Windows | PASS |

SQLite's foreign-key setting is per connection. A separate SQLite command-line connection may report `0` unless that tool enables it; the application's shared connection function executes `PRAGMA foreign_keys = ON` every time.

## D. Security and error handling

| Test case | Expected result | Actual result | Status |
| --- | --- | --- | --- |
| Anonymous writes | Cannot create, update, or delete | HTTP 401 for all three operations | PASS |
| Administrator login | Correct hashed password signs in; wrong password fails | Automated tests returned HTTP 302 and HTTP 401 respectively | PASS (temporary config) |
| CSRF | Missing token blocks state changes | HTTP 403 for create/update/delete and login/logout checks | PASS |
| Validation | Empty/invalid fields and category input rejected | HTTP 422 with field messages; no row inserted | PASS |
| Malformed JSON | Request rejected cleanly | HTTP 400 JSON after correction | PASS |
| Duplicate create | Identical repeated submission does not create another row | First POST 201, repeat POST 409, database count remained 1 after correction | PASS |
| Nonexistent ID | Read/update/delete return not found | HTTP 404 | PASS |
| Unsupported API method | Clean method error | HTTP 405 JSON after correction | PASS |
| SQL injection-like search | Input treated as text | Returned no matches; existing row remained | PASS |
| Database connection failure | No path or stack trace in public response | HTTP 500 JSON with generic message | PASS |
| Safe rendering | User data is inserted as text | JavaScript uses `textContent` and DOM nodes; browser execution not checked | PARTIAL |

Passwords are hashed with Werkzeug. The Flask session secret and password hash are loaded from an ignored local configuration file or environment; session cookies are HTTP-only and SameSite Lax, with Secure enabled for production unless explicitly disabled. The live local `instance/admin_config.json` was not present during this audit, so signing in to the current local copy still requires running `python setup_admin.py` interactively.

## Issues and corrections

1. **Repeated identical POST created duplicate records.** Added a serialized duplicate check in the create transaction and HTTP 409 response. No schema or existing records changed.
2. **Malformed JSON returned a field-validation status.** Changed it to HTTP 400 JSON.
3. **Unsupported API methods returned an HTML error.** Added a JSON HTTP 405 handler.
4. **Production debug setting was implicit.** Set `DEBUG=False` explicitly and added a configuration test.

All affected tests passed again. No database migration or destructive database change was needed.

## E. AWS EC2 readiness

| Prerequisite | Current status |
| --- | --- |
| Python 3, Flask, and dependency list | Present; local Python 3.12 and Flask 3.1.3 verified |
| WSGI entry point | `app:app` present |
| Gunicorn and Nginx configuration | Example unit and reverse-proxy file present; Linux execution not tested |
| Configurable SQLite location | `CONTACTHUB_DATABASE` supports an absolute path; EC2 example uses `/var/lib/contacthub/contacthub.db` |
| File permissions | New SQLite and administrator files use mode `0600` on Ubuntu; systemd unit uses `UMask=0077` |
| Persistent storage and backups | EBS location and backup procedure documented; no EBS volume or snapshot verified |
| Production secrets | Private administrator setup and environment configuration supported; EC2 values not provisioned |
| Public transport | Example Nginx file serves HTTP only; HTTPS is not configured |

## F. Remaining issues and required checks

| Issue | Severity | Recommended action |
| --- | --- | --- |
| Real browser CRUD, modal, responsive, keyboard, and console checks were unavailable | Medium | Run the screenshot checklist below in a desktop and mobile browser against a temporary test database |
| Gunicorn, Nginx, systemd, and Ubuntu file permissions were not executed here | Medium | Verify on the eventual Ubuntu instance before publishing |
| Public HTTP example would transmit the administrator password without TLS | High | Configure HTTPS before public sign-in; keep `CONTACTHUB_SECURE_COOKIE=true` with HTTPS |
| Current local administrator credential file is absent | Medium | Run `python setup_admin.py` and verify sign-in in a browser; do not share the password |
| Login has no rate limit for repeated password guesses | Medium | Add a shared rate limit at Nginx or in the application before opening administrator sign-in publicly |
| Public visitors can read all contact details | High for real data | Use fictional data until access/privacy requirements are defined and implemented |

## Screenshot checklist for ITP16 documentation

Capture your own screenshots of: dashboard totals and category counts; contact list and search/filter results; add form and validation error; populated edit form; delete confirmation and resulting list; administrator login and anonymous write protection; DB Browser's table structure and foreign key view; `PRAGMA integrity_check` and `PRAGMA foreign_key_check`; full passing test output; and the eventual EC2 public URL, security group, and service status only after Phase 3 is authorized and performed. Do not include passwords or private configuration values in screenshots.

## G. Final verdict

**NOT READY FOR DEPLOYMENT** as a publicly accessible application yet. The local Flask/SQLite backend and automated security checks passed, but real browser behavior and the Ubuntu service stack remain unverified, and the supplied public-IP configuration lacks HTTPS. Phase 3 can begin with those deployment and verification tasks after user approval; this report does not claim that they are complete.
