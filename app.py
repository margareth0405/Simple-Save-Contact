"""ContactHub Flask application and SQLite-backed JSON API."""

from __future__ import annotations

import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import click
from flask import Flask, abort, g, jsonify, render_template, request, session


CATEGORIES = ("Family", "Friends", "Work", "Others")
FIELDS = ("fullName", "email", "phone", "category", "address", "notes")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^[+() 0-9-]+$")
CONTACT_ID_PATTERN = re.compile(r"^CH-(\d+)$")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    production = os.environ.get("CONTACTHUB_ENV", "development").lower() == "production"
    secret_key = os.environ.get("CONTACTHUB_SECRET_KEY")
    if production and test_config is None and (
        not secret_key or len(secret_key) < 32 or secret_key.startswith("replace-")
    ):
        raise RuntimeError("Set a random CONTACTHUB_SECRET_KEY of at least 32 characters before starting production.")

    secure_cookie = os.environ.get("CONTACTHUB_SECURE_COOKIE")
    app.config.update(
        DATABASE=os.environ.get("CONTACTHUB_DATABASE", str(Path(app.instance_path) / "contacthub.sqlite3")),
        SECRET_KEY=secret_key or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production if secure_cookie is None else secure_cookie.lower() in ("1", "true", "yes"),
        TIME_ZONE=os.environ.get("CONTACTHUB_TIME_ZONE", "Asia/Manila"),
        TRUSTED_HOSTS=[host.strip() for host in os.environ.get("CONTACTHUB_TRUSTED_HOSTS", "").split(",") if host.strip()] or None,
        MAX_CONTENT_LENGTH=16 * 1024,
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)
    try:
        app.config["CONTACT_ZONE"] = ZoneInfo(app.config["TIME_ZONE"])
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(f"Invalid CONTACTHUB_TIME_ZONE: {app.config['TIME_ZONE']}") from error

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            database = Path(app.config["DATABASE"])
            database.parent.mkdir(parents=True, exist_ok=True)
            g.db = sqlite3.connect(database, timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA busy_timeout = 10000")
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(error: BaseException | None = None) -> None:
        database = g.pop("db", None)
        if database is not None:
            database.close()

    def init_db() -> None:
        get_db().execute("PRAGMA journal_mode = WAL")
        with app.open_resource("schema.sql") as schema_file:
            get_db().executescript(schema_file.read().decode("utf-8"))
        get_db().commit()

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create the SQLite tables without removing existing data."""
        init_db()
        click.echo("ContactHub database initialized.")

    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        """Insert fictional sample contacts into an empty database only."""
        init_db()
        db = get_db()
        if db.execute("SELECT 1 FROM contacts LIMIT 1").fetchone():
            click.echo("Database already has contacts; sample data was not added.")
            return
        samples = (
            ("Mia Santos", "mia.santos@example.com", "+63 917 555 0101", "Friends", "Quezon City", "Fictional sample contact."),
            ("Noah Reyes", "noah.reyes@example.com", "+63 918 555 0102", "Work", "Makati City", "Fictional project teammate."),
            ("Ava Mendoza", "ava.mendoza@example.com", "+63 919 555 0103", "Family", "Pasig City", "Fictional sample contact."),
            ("Liam Garcia", "liam.garcia@example.com", "+63 920 555 0104", "Others", "Manila", "Fictional community contact."),
            ("Sofia Cruz", "sofia.cruz@example.com", "+63 921 555 0105", "Work", "Taguig City", "Fictional professional contact."),
        )
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.executemany(
            "INSERT INTO contacts (full_name, email, phone, category, address, notes, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sample + (now,) for sample in samples),
        )
        db.commit()
        click.echo("Five fictional contacts added.")

    def csrf_token() -> str:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_writes() -> None:
        if request.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            expected = session.get("csrf_token", "")
            actual = request.headers.get("X-CSRF-Token", "")
            if not expected or not actual or not hmac.compare_digest(expected, actual):
                abort(403, description="Invalid or missing CSRF token. Refresh the page and try again.")

    @app.after_request
    def prevent_contact_caching(response):
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def api_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), error.code
        return error

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", active_page="dashboard")

    @app.get("/contacts")
    def contacts():
        return render_template("contacts.html", active_page="contacts")

    def row_to_contact(row: sqlite3.Row) -> dict:
        return {
            "id": f"CH-{row['id'] + 1000}",
            "fullName": row["full_name"],
            "email": row["email"],
            "phone": row["phone"],
            "category": row["category"],
            "address": row["address"],
            "notes": row["notes"],
            "addedAt": row["added_at"],
        }

    def database_id(contact_id: str) -> int:
        match = CONTACT_ID_PATTERN.fullmatch(contact_id)
        if not match or len(match.group(1)) > 19:
            abort(404, description="Contact not found.")
        number = int(match.group(1))
        if number <= 1000 or number > (2**63 - 1) + 1000 or contact_id != f"CH-{number}":
            abort(404, description="Contact not found.")
        return number - 1000

    def contact_row(contact_id: str) -> sqlite3.Row:
        row = get_db().execute("SELECT * FROM contacts WHERE id = ?", (database_id(contact_id),)).fetchone()
        if row is None:
            abort(404, description="Contact not found.")
        return row

    def validate_contact(data: object) -> tuple[dict, dict]:
        if not isinstance(data, dict):
            return {}, {"form": "Send a JSON object with contact fields."}
        values = {field: data.get(field, "") for field in FIELDS}
        errors = {}
        for field, value in values.items():
            if not isinstance(value, str):
                errors[field] = "Must be text."
                continue
            values[field] = value.strip()

        name = values["fullName"]
        if isinstance(name, str) and (not 2 <= len(name) <= 100 or any(ord(char) < 32 for char in name)):
            errors["fullName"] = "Enter a name with 2 to 100 printable characters."
        email = values["email"]
        if isinstance(email, str) and (not 3 <= len(email) <= 150 or not EMAIL_PATTERN.fullmatch(email)):
            errors["email"] = "Enter a valid email address (maximum 150 characters)."
        phone = values["phone"]
        if isinstance(phone, str):
            digits = re.sub(r"\D", "", phone)
            if len(phone) > 30 or not PHONE_PATTERN.fullmatch(phone) or not 7 <= len(digits) <= 15:
                errors["phone"] = "Use 7 to 15 digits with optional +, spaces, hyphens, or parentheses."
        category = values["category"]
        if isinstance(category, str) and category not in CATEGORIES:
            errors["category"] = "Choose Family, Friends, Work, or Others."
        for field, maximum in (("address", 250), ("notes", 500)):
            value = values[field]
            if isinstance(value, str) and (len(value) > maximum or any(ord(char) < 32 and char not in "\n\r\t" for char in value)):
                errors[field] = f"Use at most {maximum} printable characters."
        return values, errors

    def request_contact_data() -> tuple[dict, dict]:
        if not request.is_json:
            abort(400, description="Send JSON with Content-Type: application/json.")
        return validate_contact(request.get_json(silent=True))

    @app.get("/api/contacts")
    def list_contacts():
        search = request.args.get("search", "").strip()
        category = request.args.get("category", "").strip()
        if len(search) > 150:
            abort(400, description="Search text is too long.")
        if category and category not in CATEGORIES:
            abort(400, description="Unknown category.")
        where = []
        params = []
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(full_name LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\' OR phone LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%"] * 3)
        if category:
            where.append("category = ?")
            params.append(category)
        clause = " WHERE " + " AND ".join(where) if where else ""
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        rows = db.execute("SELECT * FROM contacts" + clause + " ORDER BY added_at DESC, id DESC", params).fetchall()
        return jsonify(contacts=[row_to_contact(row) for row in rows], total=total)

    @app.get("/api/contacts/<contact_id>")
    def get_contact(contact_id: str):
        return jsonify(contact=row_to_contact(contact_row(contact_id)))

    @app.post("/api/contacts")
    def create_contact():
        values, errors = request_contact_data()
        if errors:
            return jsonify(error="Please correct the contact fields.", fields=errors), 422
        db = get_db()
        cursor = db.execute(
            "INSERT INTO contacts (full_name, email, phone, category, address, notes, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (values["fullName"], values["email"], values["phone"], values["category"], values["address"], values["notes"], datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        db.commit()
        row = db.execute("SELECT * FROM contacts WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(contact=row_to_contact(row)), 201

    @app.put("/api/contacts/<contact_id>")
    def update_contact(contact_id: str):
        row = contact_row(contact_id)
        values, errors = request_contact_data()
        if errors:
            return jsonify(error="Please correct the contact fields.", fields=errors), 422
        db = get_db()
        db.execute(
            "UPDATE contacts SET full_name = ?, email = ?, phone = ?, category = ?, address = ?, notes = ? WHERE id = ?",
            (values["fullName"], values["email"], values["phone"], values["category"], values["address"], values["notes"], row["id"]),
        )
        db.commit()
        return jsonify(contact=row_to_contact(contact_row(contact_id)))

    @app.delete("/api/contacts/<contact_id>")
    def delete_contact(contact_id: str):
        row = contact_row(contact_id)
        db = get_db()
        db.execute("DELETE FROM contacts WHERE id = ?", (row["id"],))
        db.commit()
        return "", 204

    @app.get("/api/stats")
    def stats():
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        rows = db.execute("SELECT * FROM contacts ORDER BY added_at DESC, id DESC LIMIT 5").fetchall()
        today = datetime.now(app.config["CONTACT_ZONE"]).date()
        added_today = 0
        for row in db.execute("SELECT added_at FROM contacts"):
            try:
                if datetime.fromisoformat(row["added_at"]).astimezone(app.config["CONTACT_ZONE"]).date() == today:
                    added_today += 1
            except ValueError:
                continue
        return jsonify(total=total, addedToday=added_today, recent=[row_to_contact(row) for row in rows])

    return app


app = create_app()
