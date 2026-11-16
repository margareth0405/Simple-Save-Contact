"""Schema, migration, permission, and sample-data tests on disposable databases."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing

import pytest
from werkzeug.security import check_password_hash

from database import get_db_connection, resolve_database_path
from insert_sample_data import insert_sample_data
from setup_admin import admin_config_path, save_admin_password
from setup_database import initialize_database


@pytest.fixture
def database_path(tmp_path):
    return tmp_path / "contacthub.db"


def test_creation_foreign_keys_and_idempotent_setup(database_path):
    assert not database_path.exists()
    initialize_database(database_path)
    with closing(get_db_connection(database_path)) as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert {
            row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        } == {"categories", "contacts", "sqlite_sequence"}
        assert [
            row["name"] for row in db.execute("SELECT name FROM categories ORDER BY id")
        ] == ["Family", "Friends", "Work", "Others"]
        relationship = db.execute("PRAGMA foreign_key_list(contacts)").fetchone()
        assert (
            relationship["table"], relationship["from"], relationship["to"], relationship["on_delete"]
        ) == ("categories", "category_id", "id", "RESTRICT")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO contacts (full_name, email, phone, category_id) VALUES (?, ?, ?, ?)",
                ("Invalid Category", "invalid@example.com", "1234567890", 999),
            )
        db.rollback()
        family_id = db.execute("SELECT id FROM categories WHERE name = 'Family'").fetchone()[0]
        db.execute(
            "INSERT INTO contacts (full_name, email, phone, category_id) VALUES (?, ?, ?, ?)",
            ("Family Contact", "family@example.com", "1234567890", family_id),
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM categories WHERE id = ?", (family_id,))
        db.rollback()

    initialize_database(database_path)
    with closing(get_db_connection(database_path, read_only=True)) as db:
        assert db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 4
        assert db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 1
    if os.name != "nt":
        assert database_path.stat().st_mode & 0o777 == 0o600


def test_legacy_import_preserves_ids_and_never_reimports(database_path, tmp_path):
    old_path = tmp_path / "contacthub.sqlite3"
    with closing(sqlite3.connect(old_path)) as legacy:
        legacy.execute("""CREATE TABLE contacts (
            id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT,
            category TEXT, address TEXT, notes TEXT, added_at TEXT)""")
        legacy.execute(
            "INSERT INTO contacts VALUES (7, ?, ?, ?, ?, ?, ?, ?)",
            ("Legacy Person", "legacy@example.com", "1234567890", "Work", "Old Address", "Old Note",
             "2026-10-01T12:00:00+00:00"),
        )
        legacy.commit()
    _, count = initialize_database(database_path, legacy_path=old_path)
    assert count == 1
    with closing(get_db_connection(database_path)) as db:
        row = db.execute(
            "SELECT contacts.id, categories.name, contacts.created_at "
            "FROM contacts JOIN categories ON contacts.category_id = categories.id"
        ).fetchone()
        assert (row["id"], row["name"], row["created_at"]) == (
            7, "Work", "2026-10-01T12:00:00+00:00"
        )
        db.execute("DELETE FROM contacts")
        db.commit()
    _, count_again = initialize_database(database_path, legacy_path=old_path)
    assert count_again == 0
    with closing(get_db_connection(database_path, read_only=True)) as db:
        assert db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0
    with closing(get_db_connection(old_path, read_only=True)) as legacy:
        assert legacy.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 1


def test_sample_script_adds_only_missing_fictional_records(database_path):
    assert insert_sample_data(database_path) == 5
    assert insert_sample_data(database_path) == 0
    with closing(get_db_connection(database_path, read_only=True)) as db:
        assert db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 5


def test_admin_config_hashes_password_and_keeps_session_secret(tmp_path):
    path = tmp_path / "admin_config.json"
    save_admin_password("first-test-password", path)
    first = json.loads(path.read_text(encoding="utf-8"))
    assert "first-test-password" not in path.read_text(encoding="utf-8")
    assert check_password_hash(first["admin_password_hash"], "first-test-password")
    save_admin_password("second-test-password", path)
    second = json.loads(path.read_text(encoding="utf-8"))
    assert first["secret_key"] == second["secret_key"]
    assert not check_password_hash(second["admin_password_hash"], "first-test-password")
    assert check_password_hash(second["admin_password_hash"], "second-test-password")
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_database_and_admin_secrets_cannot_be_placed_under_static():
    with pytest.raises(ValueError):
        resolve_database_path("static/contacthub.db")
    with pytest.raises(ValueError):
        admin_config_path("static/admin_config.json")
