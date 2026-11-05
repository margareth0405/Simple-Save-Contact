"""Flask pages and SQLite-backed API for ContactHub."""

from __future__ import annotations

import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import click
from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database import get_db_connection, resolve_database_path
from insert_sample_data import insert_sample_data
from setup_admin import load_admin_config
from setup_database import initialize_database


FIELDS = ("fullName", "email", "phone", "category", "address", "notes")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^[+() 0-9-]+$")
CONTACT_ID_PATTERN = re.compile(r"^CH-(\d+)$")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    saved_config = load_admin_config()
    production = os.environ.get("CONTACTHUB_ENV", "development").lower() == "production"
    secret_key = os.environ.get("CONTACTHUB_SECRET_KEY") or saved_config.get("secret_key")
    admin_hash = os.environ.get("CONTACTHUB_ADMIN_PASSWORD_HASH") or saved_config.get("admin_password_hash")
    if production and test_config is None and (
        not isinstance(secret_key, str) or len(secret_key) < 32 or
        not isinstance(admin_hash, str) or not admin_hash.startswith(("scrypt:", "pbkdf2:"))
    ):
        raise RuntimeError("Set up a stable secret and hashed administrator password before starting production.")

    secure_cookie = os.environ.get("CONTACTHUB_SECURE_COOKIE")
    app.config.update(
        DATABASE=str(resolve_database_path()),
        DEBUG=False,
        SECRET_KEY=secret_key or secrets.token_hex(32),
        ADMIN_PASSWORD_HASH=admin_hash or "",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production if secure_cookie is None else secure_cookie.lower() in ("1", "true", "yes"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        TIME_ZONE=os.environ.get("CONTACTHUB_TIME_ZONE", "Asia/Manila"),
        TRUSTED_HOSTS=[host.strip() for host in os.environ.get("CONTACTHUB_TRUSTED_HOSTS", "").split(",") if host.strip()] or None,
        MAX_CONTENT_LENGTH=16 * 1024,
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)

    @app.template_global()
    def versioned_static(filename: str) -> str:
        """Change asset URLs when files change so browsers load the current styles."""
        version = (Path(app.static_folder) / filename).stat().st_mtime_ns
        return url_for("static", filename=filename, v=version)

    try:
        app.config["CONTACT_ZONE"] = ZoneInfo(app.config["TIME_ZONE"])
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(f"Invalid CONTACTHUB_TIME_ZONE: {app.config['TIME_ZONE']}") from error

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = get_db_connection(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(error: BaseException | None = None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create tables and import the original local database if present."""
        path, migrated = initialize_database(app.config["DATABASE"])
        click.echo(f"Database ready: {path}")
        if migrated:
            click.echo(f"Imported {migrated} existing contacts.")

    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        """Add fictional contacts without duplicating existing samples."""
        click.echo(f"Added {insert_sample_data(app.config['DATABASE'])} fictional contacts.")

    def csrf_token() -> str:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.context_processor
    def template_state() -> dict:
        return {"is_admin": bool(session.get("is_admin"))}

    @app.before_request
    def protect_writes() -> None:
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        if request.path.startswith("/api/") and not session.get("is_admin"):
            abort(401, description="Administrator sign-in is required.")
        if request.path.startswith("/api/") or request.path in ("/login", "/logout"):
            expected = session.get("csrf_token", "")
            actual = request.headers.get("X-CSRF-Token", "") or request.form.get("csrf_token", "")
            if not expected or not actual or not hmac.compare_digest(expected, actual):
                abort(403, description="Invalid or missing CSRF token. Refresh the page and try again.")

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(413)
    def api_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), error.code
        return error

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        app.logger.exception("Database operation failed")
        if request.path.startswith("/api/"):
            return jsonify(error="Database operation failed. Check setup and try again."), 500
        return "Database operation failed. Check setup and try again.", 500

    def safe_next(value: str | None) -> str:
        if value and value.startswith("/") and not value.startswith("//") and all(char.isprintable() and char != "\\" for char in value):
            parsed = urlsplit(value)
            if not parsed.scheme and not parsed.netloc:
                return value
        return url_for("contacts")

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", active_page="dashboard")

    @app.get("/contacts")
    def contacts():
        return render_template("contacts.html", active_page="contacts")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("is_admin"):
            return redirect(safe_next(request.values.get("next")))
        error = None
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            password_hash = app.config["ADMIN_PASSWORD_HASH"]
            if username == "admin" and password_hash and check_password_hash(password_hash, password):
                destination = safe_next(request.form.get("next"))
                session.clear()
                session["is_admin"] = True
                session["csrf_token"] = secrets.token_urlsafe(32)
                session.permanent = True
                return redirect(destination)
            error = "Invalid administrator username or password."
        return render_template(
            "login.html", active_page="login", error=error,
            next_path=safe_next(request.values.get("next")),
            admin_configured=bool(app.config["ADMIN_PASSWORD_HASH"]),
        ), (401 if error else 200)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("dashboard"))

    def timestamp(value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()

    def row_to_contact(row: sqlite3.Row) -> dict:
        return {
            "id": f"CH-{row['id'] + 1000}",
            "fullName": row["full_name"],
            "email": row["email"],
            "phone": row["phone"],
            "category": row["category_name"],
            "categoryId": row["category_id"],
            "address": row["address"],
            "notes": row["notes"],
            "addedAt": timestamp(row["created_at"]),
            "updatedAt": timestamp(row["updated_at"]),
        }

    def database_id(contact_id: str) -> int:
        match = CONTACT_ID_PATTERN.fullmatch(contact_id)
        if not match or len(match.group(1)) > 19:
            abort(404, description="Contact not found.")
        number = int(match.group(1))
        if number <= 1000 or number > (2**63 - 1) + 1000 or contact_id != f"CH-{number}":
            abort(404, description="Contact not found.")
        return number - 1000

    CONTACT_SELECT = """SELECT contacts.*, categories.name AS category_name
                        FROM contacts JOIN categories ON categories.id = contacts.category_id"""

    def contact_row(contact_id: str) -> sqlite3.Row:
        row = get_db().execute(CONTACT_SELECT + " WHERE contacts.id = ?", (database_id(contact_id),)).fetchone()
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
            else:
                values[field] = value.strip()
        name = values["fullName"]
        if isinstance(name, str) and (not 2 <= len(name) <= 100 or any(not char.isprintable() for char in name)):
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
        if isinstance(category, str):
            found = get_db().execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()
            if not found:
                errors["category"] = "Choose an available category."
            else:
                values["categoryId"] = found["id"]
        for field, maximum in (("address", 250), ("notes", 500)):
            value = values[field]
            if isinstance(value, str) and (len(value) > maximum or any(ord(char) < 32 and char not in "\n\r\t" for char in value)):
                errors[field] = f"Use at most {maximum} printable characters."
        return values, errors

    def request_contact_data() -> tuple[dict, dict]:
        if not request.is_json:
            abort(400, description="Send JSON with Content-Type: application/json.")
        data = request.get_json(silent=True)
        if data is None:
            abort(400, description="Send a valid JSON object.")
        return validate_contact(data)

    @app.get("/api/categories")
    def list_categories():
        rows = get_db().execute("SELECT id, name FROM categories ORDER BY id").fetchall()
        return jsonify(categories=[{"id": row["id"], "name": row["name"]} for row in rows])

    @app.get("/api/contacts")
    def list_contacts():
        search = request.args.get("search", "").strip()
        category = request.args.get("category", "").strip()
        if len(search) > 150:
            abort(400, description="Search text is too long.")
        if category and get_db().execute("SELECT 1 FROM categories WHERE name = ?", (category,)).fetchone() is None:
            abort(400, description="Unknown category.")
        where = []
        params = []
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(contacts.full_name LIKE ? ESCAPE '\\' OR contacts.email LIKE ? ESCAPE '\\' OR contacts.phone LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%"] * 3)
        if category:
            where.append("categories.name = ?")
            params.append(category)
        clause = " WHERE " + " AND ".join(where) if where else ""
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        rows = db.execute(CONTACT_SELECT + clause + " ORDER BY contacts.created_at DESC, contacts.id DESC", params).fetchall()
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
        db.execute("BEGIN IMMEDIATE")
        duplicate = db.execute(
            """SELECT 1 FROM contacts
               WHERE lower(full_name) = lower(?) AND lower(email) = lower(?) AND phone = ? LIMIT 1""",
            (values["fullName"], values["email"], values["phone"]),
        ).fetchone()
        if duplicate:
            db.rollback()
            return jsonify(error="This contact already exists."), 409
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        cursor = db.execute(
            """INSERT INTO contacts
               (full_name, email, phone, category_id, address, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (values["fullName"], values["email"], values["phone"], values["categoryId"],
             values["address"], values["notes"], now, now),
        )
        db.commit()
        return jsonify(contact=row_to_contact(contact_row(f"CH-{cursor.lastrowid + 1000}"))), 201

    @app.put("/api/contacts/<contact_id>")
    def update_contact(contact_id: str):
        row = contact_row(contact_id)
        values, errors = request_contact_data()
        if errors:
            return jsonify(error="Please correct the contact fields.", fields=errors), 422
        db = get_db()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        db.execute(
            """UPDATE contacts SET full_name = ?, email = ?, phone = ?, category_id = ?,
               address = ?, notes = ?, updated_at = ? WHERE id = ?""",
            (values["fullName"], values["email"], values["phone"], values["categoryId"],
             values["address"], values["notes"], now, row["id"]),
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

    @app.get("/api/dashboard/stats")
    @app.get("/api/stats")
    def stats():
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        rows = db.execute(CONTACT_SELECT + " ORDER BY contacts.created_at DESC, contacts.id DESC LIMIT 5").fetchall()
        category_rows = db.execute(
            """SELECT categories.name, COUNT(contacts.id) AS contact_count
               FROM categories LEFT JOIN contacts ON contacts.category_id = categories.id
               GROUP BY categories.id ORDER BY categories.id"""
        ).fetchall()
        today = datetime.now(app.config["CONTACT_ZONE"]).date()
        added_today = 0
        for row in db.execute("SELECT created_at FROM contacts"):
            try:
                created = datetime.fromisoformat(row["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if created.astimezone(app.config["CONTACT_ZONE"]).date() == today:
                    added_today += 1
            except ValueError:
                continue
        return jsonify(
            total=total, addedToday=added_today,
            recent=[row_to_contact(row) for row in rows],
            categoryCounts=[{"name": row["name"], "count": row["contact_count"]} for row in category_rows],
        )

    return app


app = create_app()
