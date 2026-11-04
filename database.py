"""Shared SQLite connection setup for the app and maintenance scripts."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = PROJECT_DIR / "instance" / "contacthub.db"
LEGACY_DATABASE = PROJECT_DIR / "instance" / "contacthub.sqlite3"


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    """Resolve configured paths from the project directory, never from static/."""
    chosen = database_path if database_path is not None else os.environ.get("CONTACTHUB_DATABASE", DEFAULT_DATABASE)
    path = Path(chosen).expanduser()
    if not path.is_absolute():
        path = PROJECT_DIR / path
    resolved = path.resolve()
    static_dir = (PROJECT_DIR / "static").resolve()
    if resolved == static_dir or static_dir in resolved.parents:
        raise ValueError("The database must be stored outside the public static directory.")
    return resolved


def get_db_connection(database_path: str | Path | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    """Return a configured connection. The caller must close it."""
    path = resolve_database_path(database_path)
    if read_only:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=10)
    else:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        was_missing = not path.exists()
        connection = sqlite3.connect(path, timeout=10)
        if was_missing and os.name != "nt":
            path.chmod(0o600)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection
    except Exception:
        connection.close()
        raise
