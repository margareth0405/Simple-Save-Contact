"""Create a private admin password hash and stable Flask session secret."""

from __future__ import annotations

import getpass
import json
import os
import secrets
import tempfile
from pathlib import Path

from werkzeug.security import generate_password_hash

from database import PROJECT_DIR


DEFAULT_ADMIN_CONFIG = PROJECT_DIR / "instance" / "admin_config.json"


def admin_config_path(path: str | Path | None = None) -> Path:
    chosen = path if path is not None else os.environ.get("CONTACTHUB_ADMIN_CONFIG", DEFAULT_ADMIN_CONFIG)
    result = Path(chosen).expanduser()
    if not result.is_absolute():
        result = PROJECT_DIR / result
    resolved = result.resolve()
    static_dir = (PROJECT_DIR / "static").resolve()
    if resolved == static_dir or static_dir in resolved.parents:
        raise ValueError("Administrator configuration must be stored outside the public static directory.")
    return resolved


def load_admin_config(path: str | Path | None = None) -> dict:
    target = admin_config_path(path)
    if not target.exists():
        return {}
    with target.open("r", encoding="utf-8") as config_file:
        values = json.load(config_file)
    if not isinstance(values, dict):
        raise ValueError("Administrator configuration must be a JSON object.")
    return values


def save_admin_password(password: str, path: str | Path | None = None) -> Path:
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("Administrator password must be 12 to 128 characters long.")
    target = admin_config_path(path)
    existing = load_admin_config(target)
    secret_key = existing.get("secret_key") or secrets.token_hex(32)
    if not isinstance(secret_key, str) or len(secret_key) < 32:
        raise ValueError("Existing session secret is invalid; no changes were made.")
    values = {"secret_key": secret_key, "admin_password_hash": generate_password_hash(password)}
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(prefix=".admin-config-", dir=target.parent)
    try:
        if os.name != "nt":
            os.chmod(temp_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as config_file:
            json.dump(values, config_file)
            config_file.write("\n")
        os.replace(temp_path, target)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        Path(temp_path).unlink(missing_ok=True)
        raise
    return target


if __name__ == "__main__":
    first = getpass.getpass("Choose an administrator password (12+ characters): ")
    second = getpass.getpass("Confirm administrator password: ")
    if first != second:
        raise SystemExit("Passwords did not match; no configuration was changed.")
    try:
        result = save_admin_password(first)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"Administrator credentials saved privately at {result}.")
