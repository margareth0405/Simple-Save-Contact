"""Authentication and persistence tests for the Flask contact API."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class ContactAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp_dir.name) / "contacthub.db")
        self.config = {
            "TESTING": True,
            "DATABASE": self.database,
            "SECRET_KEY": "stable-test-secret-key-for-restarts",
            "ADMIN_PASSWORD_HASH": generate_password_hash("strong-test-password"),
        }
        initialize_database(self.database)
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def csrf(self, client=None):
        client = client or self.client
        client.get("/login")
        with client.session_transaction() as browser_session:
            return browser_session["csrf_token"]

    def login(self, client=None):
        client = client or self.client
        return client.post("/login", data={
            "username": "admin", "password": "strong-test-password", "csrf_token": self.csrf(client),
        })

    def test_anonymous_reads_and_write_protection(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/contacts").status_code, 200)
        self.assertEqual(self.client.get("/api/contacts").status_code, 200)
        categories = self.client.get("/api/categories").json["categories"]
        self.assertEqual([item["name"] for item in categories], ["Family", "Friends", "Work", "Others"])
        self.assertEqual(self.client.post("/api/contacts", json=CONTACT).status_code, 401)
        self.assertEqual(self.client.put("/api/contacts/CH-1001", json=CONTACT).status_code, 401)
        self.assertEqual(self.client.delete("/api/contacts/CH-1001").status_code, 401)

    def test_login_logout_and_csrf(self):
        token = self.csrf()
        self.assertEqual(self.client.post("/login", data={"username": "admin", "password": "wrong"}).status_code, 403)
        wrong = self.client.post("/login", data={
            "username": "admin", "password": "wrong", "csrf_token": token,
        })
        self.assertEqual(wrong.status_code, 401)
        self.assertIn(b"Invalid administrator", wrong.data)
        signed_in = self.login()
        self.assertEqual(signed_in.status_code, 302)
        self.assertIn(b"Sign out", self.client.get("/contacts").data)
        token = self.csrf()
        self.assertEqual(self.client.post("/api/contacts", json=CONTACT).status_code, 403)
        created = self.client.post("/api/contacts", json=CONTACT, headers={"X-CSRF-Token": token})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post("/logout").status_code, 403)
        self.assertEqual(self.client.post("/logout", data={"csrf_token": token}).status_code, 302)
        self.assertEqual(self.client.delete(f"/api/contacts/{created.json['contact']['id']}").status_code, 401)

    def test_records_and_stats_survive_new_app_instance(self):
        self.assertEqual(self.login().status_code, 302)
        token = self.csrf()
        created = self.client.post("/api/contacts", json=CONTACT, headers={"X-CSRF-Token": token})
        contact_id = created.json["contact"]["id"]
        first_stats = self.client.get("/api/dashboard/stats").json
        self.assertEqual(first_stats["total"], 1)
        self.assertEqual(first_stats["addedToday"], 1)
        self.assertEqual(next(item["count"] for item in first_stats["categoryCounts"] if item["name"] == "Family"), 1)

        restarted = create_app(self.config)
        second_client = restarted.test_client()
        fetched = second_client.get(f"/api/contacts/{contact_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json["contact"]["fullName"], CONTACT["fullName"])
        self.assertEqual(second_client.get("/api/dashboard/stats").json["total"], 1)

    def test_login_redirect_stays_on_this_site(self):
        self.csrf()
        response = self.client.post("/login", data={
            "username": "admin", "password": "strong-test-password",
            "csrf_token": self.csrf(), "next": "//example.com/steal",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/contacts")

    def test_generated_admin_config_is_used_by_flask(self):
        config_path = Path(self.temp_dir.name) / "admin_config.json"
        save_admin_password("configured-test-password", config_path)
        with patch.dict(os.environ, {"CONTACTHUB_ADMIN_CONFIG": str(config_path)}):
            configured_app = create_app({"TESTING": True, "DATABASE": self.database})
        browser = configured_app.test_client()
        browser.get("/login")
        with browser.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        response = browser.post("/login", data={
            "username": "admin", "password": "configured-test-password", "csrf_token": token,
        })
        self.assertEqual(response.status_code, 302)


if __name__ == "__main__":
    unittest.main()
