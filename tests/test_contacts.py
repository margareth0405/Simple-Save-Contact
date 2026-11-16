"""Authentication and persistence tests for the Flask contact API."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from setup_admin import save_admin_password
from setup_database import initialize_database


CONTACT = {
    "fullName": "Fictional Contact",
    "email": "fictional@example.com",
    "phone": "09175550123",
    "category": "Family",
    "address": "Sample Address",
    "notes": "Test only",
}


@pytest.fixture
def access(tmp_path):
    database = str(tmp_path / "contacthub.db")
    config = {
        "TESTING": True,
        "DATABASE": database,
        "SECRET_KEY": "stable-test-secret-key-for-restarts",
        "ADMIN_PASSWORD_HASH": generate_password_hash("strong-test-password"),
    }
    initialize_database(database)
    app = create_app(config)
    client = app.test_client()

    def csrf(selected_client=None):
        selected_client = selected_client or client
        selected_client.get("/login")
        with selected_client.session_transaction() as browser_session:
            return browser_session["csrf_token"]

    def login(selected_client=None):
        selected_client = selected_client or client
        return selected_client.post("/login", data={
            "username": "admin",
            "password": "strong-test-password",
            "csrf_token": csrf(selected_client),
        })

    return SimpleNamespace(
        app=app, client=client, config=config, database=database, csrf=csrf, login=login
    )


def test_anonymous_reads_and_write_protection(access):
    assert access.client.get("/").status_code == 200
    assert access.client.get("/contacts").status_code == 200
    assert access.client.get("/api/contacts").status_code == 200
    categories = access.client.get("/api/categories").json["categories"]
    assert [item["name"] for item in categories] == ["Family", "Friends", "Work", "Others"]
    assert access.client.post("/api/contacts", json=CONTACT).status_code == 401
    assert access.client.put("/api/contacts/CH-1001", json=CONTACT).status_code == 401
    assert access.client.delete("/api/contacts/CH-1001").status_code == 401


def test_login_logout_and_csrf(access):
    token = access.csrf()
    assert access.client.post("/login", data={"username": "admin", "password": "wrong"}).status_code == 403
    wrong = access.client.post("/login", data={
        "username": "admin", "password": "wrong", "csrf_token": token,
    })
    assert wrong.status_code == 401
    assert b"Invalid administrator" in wrong.data
    assert access.login().status_code == 302
    assert b"Sign out" in access.client.get("/contacts").data
    token = access.csrf()
    assert access.client.post("/api/contacts", json=CONTACT).status_code == 403
    created = access.client.post(
        "/api/contacts", json=CONTACT, headers={"X-CSRF-Token": token}
    )
    assert created.status_code == 201
    assert access.client.post("/logout").status_code == 403
    assert access.client.post("/logout", data={"csrf_token": token}).status_code == 302
    assert access.client.delete(f"/api/contacts/{created.json['contact']['id']}").status_code == 401


def test_records_and_stats_survive_new_app_instance(access):
    assert access.login().status_code == 302
    token = access.csrf()
    created = access.client.post(
        "/api/contacts", json=CONTACT, headers={"X-CSRF-Token": token}
    )
    contact_id = created.json["contact"]["id"]
    first_stats = access.client.get("/api/dashboard/stats").json
    assert first_stats["total"] == 1
    assert first_stats["addedToday"] == 1
    assert next(
        item["count"] for item in first_stats["categoryCounts"] if item["name"] == "Family"
    ) == 1

    second_client = create_app(access.config).test_client()
    fetched = second_client.get(f"/api/contacts/{contact_id}")
    assert fetched.status_code == 200
    assert fetched.json["contact"]["fullName"] == CONTACT["fullName"]
    assert second_client.get("/api/dashboard/stats").json["total"] == 1


def test_login_redirect_stays_on_this_site(access):
    response = access.client.post("/login", data={
        "username": "admin",
        "password": "strong-test-password",
        "csrf_token": access.csrf(),
        "next": "//example.com/steal",
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/contacts"


def test_generated_admin_config_is_used_by_flask(access, tmp_path, monkeypatch):
    config_path = tmp_path / "admin_config.json"
    save_admin_password("configured-test-password", config_path)
    monkeypatch.setenv("CONTACTHUB_ADMIN_CONFIG", str(config_path))
    configured_app = create_app({"TESTING": True, "DATABASE": access.database})
    browser = configured_app.test_client()
    browser.get("/login")
    with browser.session_transaction() as browser_session:
        token = browser_session["csrf_token"]
    response = browser.post("/login", data={
        "username": "admin", "password": "configured-test-password", "csrf_token": token,
    })
    assert response.status_code == 302


def test_production_configuration_disables_debug_and_secures_session_cookie(access, monkeypatch):
    monkeypatch.setenv("CONTACTHUB_ENV", "production")
    monkeypatch.setenv("CONTACTHUB_SECURE_COOKIE", "true")
    production_app = create_app(access.config)
    assert not production_app.debug
    assert production_app.config["SESSION_COOKIE_HTTPONLY"]
    assert production_app.config["SESSION_COOKIE_SECURE"]
    assert production_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
