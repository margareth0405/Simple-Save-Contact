"""Create ContactHub tables and preserve data from the original local database."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from database import DEFAULT_DATABASE, LEGACY_DATABASE, PROJECT_DIR, get_db_connection, resolve_database_path


DEFAULT_CATEGORIES = ("Family", "Friends", "Work", "Others")


def _import_legacy(db: sqlite3.Connection, legacy_path: Path) -> int:
    """Copy old Phase 2 rows into a new database; never change the old file."""
    with closing(get_db_connection(legacy_path, read_only=True)) as legacy:
        columns = {row["name"] for row in legacy.execute("PRAGMA table_info(contacts)")}
        expected = {"id", "full_name", "email", "phone", "category", "address", "notes", "added_at"}
        if not expected.issubset(columns):
            raise RuntimeError("Legacy database has an unexpected contacts schema; no records were imported.")
        categories = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM categories")}
        count = 0
        for row in legacy.execute("SELECT id, full_name, email, phone, category, address, notes, added_at FROM contacts ORDER BY id"):
            category_id = categories.get(row["category"])
            if category_id is None:
                raise RuntimeError(f"Legacy contact {row['id']} has an unknown category; no records were imported.")
            db.execute(
                """INSERT INTO contacts
                   (id, full_name, email, phone, category_id, address, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["full_name"], row["email"], row["phone"], category_id,
                 row["address"] or "", row["notes"] or "", row["added_at"], row["added_at"]),
            )
            count += 1
        return count


def initialize_database(database_path: str | Path | None = None, *, legacy_path: str | Path | None = None) -> tuple[Path, int]:
    """Create missing tables, seed category names, and migrate legacy rows once."""
    target = resolve_database_path(database_path)
    origin = resolve_database_path(legacy_path) if legacy_path is not None else (
        LEGACY_DATABASE if target == DEFAULT_DATABASE else None
    )
    migrated = 0
    with closing(get_db_connection(target)) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript((PROJECT_DIR / "schema.sql").read_text(encoding="utf-8"))
        try:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(contacts)")}
            if "category_id" not in columns:
                raise RuntimeError("This database has the old contacts schema. Use a new contacthub.db path; the old file was not changed.")
            db.executemany("INSERT OR IGNORE INTO categories (name) VALUES (?)", ((name,) for name in DEFAULT_CATEGORIES))
            needs_initial_setup = db.execute("PRAGMA user_version").fetchone()[0] == 0
            is_empty = db.execute("SELECT 1 FROM contacts LIMIT 1").fetchone() is None
            if needs_initial_setup and is_empty and origin is not None and origin.exists() and origin != target:
                migrated = _import_legacy(db, origin)
            db.execute("PRAGMA user_version = 1")
            db.commit()
        except Exception:
            db.rollback()
            raise
    return target, migrated


if __name__ == "__main__":
    path, migrated = initialize_database()
    print(f"Database ready: {path}")
    if migrated:
        print(f"Imported {migrated} existing contacts; the original database was left unchanged.")
