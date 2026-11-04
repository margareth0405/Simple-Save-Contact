"""Schema, migration, permission, and sample-data tests on disposable databases."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from werkzeug.security import check_password_hash

from database import get_db_connection, resolve_database_path
from insert_sample_data import insert_sample_data
from setup_admin import admin_config_path, save_admin_password
from setup_database import initialize_database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "contacthub.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_creation_foreign_keys_and_idempotent_setup(self):
        self.assertFalse(self.path.exists())
        initialize_database(self.path)
        with closing(get_db_connection(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual({row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")},
                             {"categories", "contacts", "sqlite_sequence"})
            self.assertEqual([row["name"] for row in db.execute("SELECT name FROM categories ORDER BY id")],
                             ["Family", "Friends", "Work", "Others"])
            relationship = db.execute("PRAGMA foreign_key_list(contacts)").fetchone()
            self.assertEqual((relationship["table"], relationship["from"], relationship["to"], relationship["on_delete"]),
                             ("categories", "category_id", "id", "RESTRICT"))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO contacts (full_name, email, phone, category_id) VALUES (?, ?, ?, ?)",
                           ("Invalid Category", "invalid@example.com", "1234567890", 999))
            db.rollback()
            family_id = db.execute("SELECT id FROM categories WHERE name = 'Family'").fetchone()[0]
            db.execute("INSERT INTO contacts (full_name, email, phone, category_id) VALUES (?, ?, ?, ?)",
                       ("Family Contact", "family@example.com", "1234567890", family_id))
            db.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM categories WHERE id = ?", (family_id,))
            db.rollback()

        initialize_database(self.path)
        with closing(get_db_connection(self.path, read_only=True)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM categories").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 1)
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_legacy_import_preserves_ids_and_never_reimports(self):
        old_path = Path(self.temp_dir.name) / "contacthub.sqlite3"
        with closing(sqlite3.connect(old_path)) as legacy:
            legacy.execute("""CREATE TABLE contacts (
                id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT,
                category TEXT, address TEXT, notes TEXT, added_at TEXT)""")
            legacy.execute("INSERT INTO contacts VALUES (7, ?, ?, ?, ?, ?, ?, ?)",
                           ("Legacy Person", "legacy@example.com", "1234567890", "Work", "Old Address", "Old Note",
                            "2026-10-01T12:00:00+00:00"))
            legacy.commit()
        _, count = initialize_database(self.path, legacy_path=old_path)
        self.assertEqual(count, 1)
        with closing(get_db_connection(self.path)) as db:
            row = db.execute("SELECT contacts.id, categories.name, contacts.created_at FROM contacts JOIN categories ON contacts.category_id = categories.id").fetchone()
            self.assertEqual((row["id"], row["name"], row["created_at"]),
                             (7, "Work", "2026-10-01T12:00:00+00:00"))
            db.execute("DELETE FROM contacts")
            db.commit()
        _, count_again = initialize_database(self.path, legacy_path=old_path)
        self.assertEqual(count_again, 0)
        with closing(get_db_connection(self.path, read_only=True)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 0)
        with closing(get_db_connection(old_path, read_only=True)) as legacy:
            self.assertEqual(legacy.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 1)

    def test_sample_script_adds_only_missing_fictional_records(self):
        self.assertEqual(insert_sample_data(self.path), 5)
        self.assertEqual(insert_sample_data(self.path), 0)
        with closing(get_db_connection(self.path, read_only=True)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 5)

    def test_admin_config_hashes_password_and_keeps_session_secret(self):
        path = Path(self.temp_dir.name) / "admin_config.json"
        save_admin_password("first-test-password", path)
        first = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("first-test-password", path.read_text(encoding="utf-8"))
        self.assertTrue(check_password_hash(first["admin_password_hash"], "first-test-password"))
        save_admin_password("second-test-password", path)
        second = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(first["secret_key"], second["secret_key"])
        self.assertFalse(check_password_hash(second["admin_password_hash"], "first-test-password"))
        self.assertTrue(check_password_hash(second["admin_password_hash"], "second-test-password"))
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_database_and_admin_secrets_cannot_be_placed_under_static(self):
        with self.assertRaises(ValueError):
            resolve_database_path("static/contacthub.db")
        with self.assertRaises(ValueError):
            admin_config_path("static/admin_config.json")
