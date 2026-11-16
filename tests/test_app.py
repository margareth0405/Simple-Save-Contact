"""End-to-end Flask request tests using a fresh SQLite file for every test."""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from app import create_app


VALID_CONTACT = {
    "fullName": "Test Person",
    "email": "test.person@example.com",
    "phone": "+63 917 555 0123",
    "category": "Friends",
    "address": "Fictional Street",
    "notes": "Test record only.",
}


@pytest.fixture
def contact_hub(tmp_path):
    database = str(tmp_path / "test.sqlite3")
    app = create_app({
        "TESTING": True,
        "DATABASE": database,
        "SECRET_KEY": "test-only-secret",
        "ADMIN_PASSWORD_HASH": generate_password_hash("testing-password-123"),
    })
    client = app.test_client()
    result = app.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code == 0, result.output
    client.get("/login")
    with client.session_transaction() as browser_session:
        login_csrf = browser_session["csrf_token"]
    login_result = client.post("/login", data={
        "username": "admin",
        "password": "testing-password-123",
        "csrf_token": login_csrf,
    })
    assert login_result.status_code == 302
    client.get("/contacts")
    with client.session_transaction() as browser_session:
        csrf = browser_session["csrf_token"]

    def write(method, path, data=None, include_csrf=True):
        headers = {"X-CSRF-Token": csrf} if include_csrf else {}
        return client.open(path, method=method, json=data, headers=headers)

    return SimpleNamespace(app=app, client=client, csrf=csrf, database=database, write=write)


def test_pages_render_with_shared_layout_and_static_assets(contact_hub):
    dashboard = contact_hub.client.get("/")
    contacts = contact_hub.client.get("/contacts")
    assert dashboard.status_code == 200
    assert contacts.status_code == 200
    assert b"Dashboard | ContactHub" in dashboard.data
    assert b"Contacts | ContactHub" in contacts.data
    assert b"/static/css/style.css" in contacts.data
    assert b"/static/js/app.js" in contacts.data
    assert b"/static/js/theme.js" in contacts.data
    assert b'id="themeToggle"' in contacts.data
    assert contacts.data.count(b'class="theme-icon"') == 1
    markup = contacts.get_data(as_text=True)
    assert re.search(r"/static/css/style\.css\?v=\d+", markup)
    assert re.search(r"/static/js/theme\.js\?v=\d+", markup)
    assert re.search(r'<meta name="csrf-token" content="[^"]+">', markup)
    assert b"localStorage" not in contacts.data
    assert contact_hub.client.get("/static/js/app.js").status_code == 200
    assert contact_hub.client.get("/static/js/theme.js").status_code == 200


def test_create_read_update_delete_and_database_persistence(contact_hub):
    created = contact_hub.write("POST", "/api/contacts", VALID_CONTACT)
    assert created.status_code == 201, created.json
    contact = created.json["contact"]
    assert contact["id"] == "CH-1001"
    assert contact["fullName"] == VALID_CONTACT["fullName"]

    listed = contact_hub.client.get("/api/contacts")
    assert listed.status_code == 200
    assert listed.json["total"] == 1
    assert listed.json["contacts"][0]["id"] == contact["id"]
    detail = contact_hub.client.get(f"/api/contacts/{contact['id']}").json["contact"]
    assert detail["email"] == VALID_CONTACT["email"]

    with closing(sqlite3.connect(contact_hub.database)) as db:
        assert db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 1

    updated_values = {
        **VALID_CONTACT, "fullName": "Renamed Person", "category": "Work", "notes": "Updated."
    }
    updated = contact_hub.write("PUT", f"/api/contacts/{contact['id']}", updated_values)
    assert updated.status_code == 200, updated.json
    assert updated.json["contact"]["fullName"] == "Renamed Person"
    assert updated.json["contact"]["addedAt"] == contact["addedAt"]
    assert updated.json["contact"]["updatedAt"] != contact["updatedAt"]
    with closing(sqlite3.connect(contact_hub.database)) as db:
        category = db.execute(
            "SELECT categories.name FROM contacts "
            "JOIN categories ON categories.id = contacts.category_id"
        ).fetchone()[0]
        assert category == "Work"

    stats = contact_hub.client.get("/api/stats").json
    assert stats["total"] == 1
    assert stats["addedToday"] == 1
    assert stats["recent"][0]["category"] == "Work"
    assert next(item["count"] for item in stats["categoryCounts"] if item["name"] == "Work") == 1

    deleted = contact_hub.write("DELETE", f"/api/contacts/{contact['id']}")
    assert deleted.status_code == 204
    assert contact_hub.client.get("/api/contacts").json["total"] == 0
    assert contact_hub.client.get(f"/api/contacts/{contact['id']}").status_code == 404
    assert contact_hub.client.get("/api/contacts/CH-999999999999999999999999999999").status_code == 404
    assert contact_hub.write("PUT", f"/api/contacts/{contact['id']}", VALID_CONTACT).status_code == 404
    assert contact_hub.write("DELETE", f"/api/contacts/{contact['id']}").status_code == 404

    second = contact_hub.write("POST", "/api/contacts", VALID_CONTACT)
    assert second.status_code == 201
    assert second.json["contact"]["id"] == "CH-1002"


def test_search_filter_and_literal_wildcards(contact_hub):
    records = [
        {**VALID_CONTACT, "fullName": "Mia Santos", "email": "mia@example.com", "phone": "111 222 3333", "category": "Family"},
        {**VALID_CONTACT, "fullName": "Noah Reyes", "email": "noah@example.com", "phone": "444 555 6666", "category": "Work"},
        {**VALID_CONTACT, "fullName": "Ava %", "email": "ava@example.com", "phone": "777 888 9999", "category": "Friends"},
    ]
    for record in records:
        assert contact_hub.write("POST", "/api/contacts", record).status_code == 201
    for path, expected_name in (
        ("/api/contacts?search=mia", "Mia Santos"),
        ("/api/contacts?search=noah%40example.com", "Noah Reyes"),
        ("/api/contacts?search=777", "Ava %"),
        ("/api/contacts?search=%25", "Ava %"),
        ("/api/contacts?category=Work", "Noah Reyes"),
        ("/api/contacts?search=Noah&category=Work", "Noah Reyes"),
    ):
        result = contact_hub.client.get(path)
        assert result.status_code == 200, path
        assert result.json["total"] == 3, path
        assert [item["fullName"] for item in result.json["contacts"]] == [expected_name], path
    assert contact_hub.client.get("/api/contacts?category=NotValid").status_code == 400


def test_server_validation_blocks_invalid_data_without_writing(contact_hub):
    invalid_cases = (
        ({**VALID_CONTACT, "fullName": "A"}, "fullName"),
        ({**VALID_CONTACT, "email": "not-an-email"}, "email"),
        ({**VALID_CONTACT, "phone": "123"}, "phone"),
        ({**VALID_CONTACT, "phone": "123\n4567890"}, "phone"),
        ({**VALID_CONTACT, "category": "Unknown"}, "category"),
        ({**VALID_CONTACT, "category": 999}, "category"),
        ({**VALID_CONTACT, "notes": "x" * 501}, "notes"),
        ({**VALID_CONTACT, "fullName": 42}, "fullName"),
        ({"fullName": "Only Name"}, "email"),
    )
    for value, field in invalid_cases:
        result = contact_hub.write("POST", "/api/contacts", value)
        assert result.status_code == 422, (field, result.json)
        assert field in result.json["fields"]
    assert contact_hub.client.get("/api/contacts").json["total"] == 0
    response = contact_hub.client.post(
        "/api/contacts", data="not json", headers={"X-CSRF-Token": contact_hub.csrf}
    )
    assert response.status_code == 400


def test_update_rejects_invalid_values_and_preserves_record(contact_hub):
    contact_id = contact_hub.write("POST", "/api/contacts", VALID_CONTACT).json["contact"]["id"]
    invalid = contact_hub.write(
        "PUT", f"/api/contacts/{contact_id}", {**VALID_CONTACT, "email": "bad"}
    )
    assert invalid.status_code == 422
    saved = contact_hub.client.get(f"/api/contacts/{contact_id}").json["contact"]
    assert saved["email"] == VALID_CONTACT["email"]


def test_csrf_is_required_for_every_write(contact_hub):
    assert contact_hub.write(
        "POST", "/api/contacts", VALID_CONTACT, include_csrf=False
    ).status_code == 403
    contact_id = contact_hub.write("POST", "/api/contacts", VALID_CONTACT).json["contact"]["id"]
    assert contact_hub.write(
        "PUT", f"/api/contacts/{contact_id}", VALID_CONTACT, include_csrf=False
    ).status_code == 403
    assert contact_hub.write(
        "DELETE", f"/api/contacts/{contact_id}", include_csrf=False
    ).status_code == 403
    assert contact_hub.client.get("/api/contacts").json["total"] == 1


def test_demo_seed_is_explicit_and_does_not_overwrite_data(contact_hub):
    runner = contact_hub.app.test_cli_runner()
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    assert contact_hub.client.get("/api/contacts").json["total"] == 5
    second = runner.invoke(args=["seed-demo"])
    assert "Added 0" in second.output
    assert contact_hub.client.get("/api/contacts").json["total"] == 5


def test_repeated_create_returns_conflict_without_duplicate_record(contact_hub):
    first = contact_hub.write("POST", "/api/contacts", VALID_CONTACT)
    second = contact_hub.write("POST", "/api/contacts", VALID_CONTACT)
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json["error"] == "This contact already exists."
    assert contact_hub.client.get("/api/contacts").json["total"] == 1


def test_malformed_requests_and_unsupported_methods_are_json_errors(contact_hub):
    malformed = contact_hub.client.post(
        "/api/contacts",
        data="{not json",
        content_type="application/json",
        headers={"X-CSRF-Token": contact_hub.csrf},
    )
    assert malformed.status_code == 400
    assert malformed.mimetype == "application/json"
    assert contact_hub.client.post(
        "/api/contacts", json=[], headers={"X-CSRF-Token": contact_hub.csrf}
    ).status_code == 422
    unsupported = contact_hub.client.patch(
        "/api/contacts", json=VALID_CONTACT, headers={"X-CSRF-Token": contact_hub.csrf}
    )
    assert unsupported.status_code == 405
    assert unsupported.mimetype == "application/json"
    assert contact_hub.client.get("/api/contacts/CH-9999").status_code == 404
    assert contact_hub.client.get("/api/contacts").json["total"] == 0


def test_sql_injection_like_search_remains_literal(contact_hub):
    assert contact_hub.write("POST", "/api/contacts", VALID_CONTACT).status_code == 201
    result = contact_hub.client.get("/api/contacts", query_string={"search": "' OR 1=1 --"})
    assert result.status_code == 200
    assert result.json["contacts"] == []
    assert result.json["total"] == 1


def test_database_connection_error_returns_generic_json(tmp_path, caplog):
    broken = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path),
        "SECRET_KEY": "test-only-secret",
        "ADMIN_PASSWORD_HASH": generate_password_hash("testing-password-123"),
    })
    with caplog.at_level(logging.ERROR, logger=broken.logger.name):
        response = broken.test_client().get("/api/contacts")
    assert "Database operation failed" in caplog.text
    assert response.status_code == 500
    assert response.mimetype == "application/json"
    assert str(tmp_path) not in response.get_data(as_text=True)
    assert "Traceback" not in response.get_data(as_text=True)
