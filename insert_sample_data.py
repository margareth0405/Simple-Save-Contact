"""Add fictional examples without duplicating records or changing existing ones."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from database import get_db_connection
from setup_database import initialize_database


SAMPLES = (
    ("Mia Santos", "mia.santos@example.com", "+63 917 555 0101", "Friends", "Quezon City", "Fictional sample contact."),
    ("Noah Reyes", "noah.reyes@example.com", "+63 918 555 0102", "Work", "Makati City", "Fictional project teammate."),
    ("Ava Mendoza", "ava.mendoza@example.com", "+63 919 555 0103", "Family", "Pasig City", "Fictional sample contact."),
    ("Liam Garcia", "liam.garcia@example.com", "+63 920 555 0104", "Others", "Manila", "Fictional community contact."),
    ("Sofia Cruz", "sofia.cruz@example.com", "+63 921 555 0105", "Work", "Taguig City", "Fictional professional contact."),
)


def insert_sample_data(database_path: str | Path | None = None) -> int:
    target, _ = initialize_database(database_path)
    added = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(get_db_connection(target)) as db:
        categories = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM categories")}
        try:
            for name, email, phone, category, address, notes in SAMPLES:
                existing = db.execute("SELECT 1 FROM contacts WHERE lower(email) = lower(?) LIMIT 1", (email,)).fetchone()
                if existing:
                    continue
                db.execute(
                    """INSERT INTO contacts
                       (full_name, email, phone, category_id, address, notes, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, email, phone, categories[category], address, notes, now, now),
                )
                added += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
    return added


if __name__ == "__main__":
    print(f"Added {insert_sample_data()} fictional contacts.")
