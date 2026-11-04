"""End-to-end Flask request tests using a fresh SQLite file for every test."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app
from werkzeug.security import generate_password_hash


VALID_CONTACT = {
    "fullName": "Test Person",
    "email": "test.person@example.com",
    "phone": "+63 917 555 0123",
    "category": "Friends",
    "address": "Fictional Street",
    "notes": "Test record only.",
}


class ContactHubTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp_dir.name) / "test.sqlite3")
        self.app = create_app({
            "TESTING": True,
            "DATABASE": self.database,
            "SECRET_KEY": "test-only-secret",
            "ADMIN_PASSWORD_HASH": generate_password_hash("testing-password-123"),
        })
        self.client = self.app.test_client()
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.client.get("/login")
        with self.client.session_transaction() as browser_session:
            login_csrf = browser_session["csrf_token"]
        login_result = self.client.post("/login", data={
            "username": "admin", "password": "testing-password-123", "csrf_token": login_csrf,
        })
        self.assertEqual(login_result.status_code, 302)
        self.client.get("/contacts")
        with self.client.session_transaction() as browser_session:
            self.csrf = browser_session["csrf_token"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, method, path, data=None, csrf=True):
        headers = {"X-CSRF-Token": self.csrf} if csrf else {}
        return self.client.open(path, method=method, json=data, headers=headers)

    def test_pages_render_with_shared_layout_and_static_assets(self):
        dashboard = self.client.get("/")
        contacts = self.client.get("/contacts")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(contacts.status_code, 200)
        self.assertIn(b"Dashboard | ContactHub", dashboard.data)
        self.assertIn(b"Contacts | ContactHub", contacts.data)
        self.assertIn(b"/static/css/style.css", contacts.data)
        self.assertIn(b"/static/js/app.js", contacts.data)
        self.assertRegex(contacts.data.decode(), r'<meta name="csrf-token" content="[^"]+">')
        self.assertNotIn(b"localStorage", contacts.data)
        asset = self.client.get("/static/js/app.js")
        self.assertEqual(asset.status_code, 200)
        asset.close()

    def test_create_read_update_delete_and_database_persistence(self):
        created = self.write("POST", "/api/contacts", VALID_CONTACT)
        self.assertEqual(created.status_code, 201, created.json)
        contact = created.json["contact"]
        self.assertEqual(contact["id"], "CH-1001")
        self.assertEqual(contact["fullName"], VALID_CONTACT["fullName"])

        listed = self.client.get("/api/contacts")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json["total"], 1)
        self.assertEqual(listed.json["contacts"][0]["id"], contact["id"])
        self.assertEqual(self.client.get(f"/api/contacts/{contact['id']}").json["contact"]["email"], VALID_CONTACT["email"])

        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 1)

        updated_values = {**VALID_CONTACT, "fullName": "Renamed Person", "category": "Work", "notes": "Updated."}
        updated = self.write("PUT", f"/api/contacts/{contact['id']}", updated_values)
        self.assertEqual(updated.status_code, 200, updated.json)
        self.assertEqual(updated.json["contact"]["fullName"], "Renamed Person")
        self.assertEqual(updated.json["contact"]["addedAt"], contact["addedAt"])
        self.assertNotEqual(updated.json["contact"]["updatedAt"], contact["updatedAt"])
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT categories.name FROM contacts JOIN categories ON categories.id = contacts.category_id").fetchone()[0], "Work")

        stats = self.client.get("/api/stats").json
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["addedToday"], 1)
        self.assertEqual(stats["recent"][0]["category"], "Work")
        self.assertEqual(next(item["count"] for item in stats["categoryCounts"] if item["name"] == "Work"), 1)

        deleted = self.write("DELETE", f"/api/contacts/{contact['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/contacts").json["total"], 0)
        self.assertEqual(self.client.get(f"/api/contacts/{contact['id']}").status_code, 404)
        self.assertEqual(self.client.get("/api/contacts/CH-999999999999999999999999999999").status_code, 404)
        self.assertEqual(self.write("PUT", f"/api/contacts/{contact['id']}", VALID_CONTACT).status_code, 404)
        self.assertEqual(self.write("DELETE", f"/api/contacts/{contact['id']}").status_code, 404)

        second = self.write("POST", "/api/contacts", VALID_CONTACT)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.json["contact"]["id"], "CH-1002")

    def test_search_filter_and_literal_wildcards(self):
        records = [
            {**VALID_CONTACT, "fullName": "Mia Santos", "email": "mia@example.com", "phone": "111 222 3333", "category": "Family"},
            {**VALID_CONTACT, "fullName": "Noah Reyes", "email": "noah@example.com", "phone": "444 555 6666", "category": "Work"},
            {**VALID_CONTACT, "fullName": "Ava %", "email": "ava@example.com", "phone": "777 888 9999", "category": "Friends"},
        ]
        for record in records:
            self.assertEqual(self.write("POST", "/api/contacts", record).status_code, 201)
        for path, expected_name in (
            ("/api/contacts?search=mia", "Mia Santos"),
            ("/api/contacts?search=noah%40example.com", "Noah Reyes"),
            ("/api/contacts?search=777", "Ava %"),
            ("/api/contacts?search=%25", "Ava %"),
            ("/api/contacts?category=Work", "Noah Reyes"),
            ("/api/contacts?search=Noah&category=Work", "Noah Reyes"),
        ):
            with self.subTest(path=path):
                result = self.client.get(path)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json["total"], 3)
                self.assertEqual([item["fullName"] for item in result.json["contacts"]], [expected_name])
        self.assertEqual(self.client.get("/api/contacts?category=NotValid").status_code, 400)

    def test_server_validation_blocks_invalid_data_without_writing(self):
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
            with self.subTest(field=field, value=str(value)[:40]):
                result = self.write("POST", "/api/contacts", value)
                self.assertEqual(result.status_code, 422, result.json)
                self.assertIn(field, result.json["fields"])
        self.assertEqual(self.client.get("/api/contacts").json["total"], 0)
        self.assertEqual(self.client.post("/api/contacts", data="not json", headers={"X-CSRF-Token": self.csrf}).status_code, 400)

    def test_update_rejects_invalid_values_and_preserves_record(self):
        contact_id = self.write("POST", "/api/contacts", VALID_CONTACT).json["contact"]["id"]
        invalid = self.write("PUT", f"/api/contacts/{contact_id}", {**VALID_CONTACT, "email": "bad"})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(self.client.get(f"/api/contacts/{contact_id}").json["contact"]["email"], VALID_CONTACT["email"])

    def test_csrf_is_required_for_every_write(self):
        self.assertEqual(self.write("POST", "/api/contacts", VALID_CONTACT, csrf=False).status_code, 403)
        contact_id = self.write("POST", "/api/contacts", VALID_CONTACT).json["contact"]["id"]
        self.assertEqual(self.write("PUT", f"/api/contacts/{contact_id}", VALID_CONTACT, csrf=False).status_code, 403)
        self.assertEqual(self.write("DELETE", f"/api/contacts/{contact_id}", csrf=False).status_code, 403)
        self.assertEqual(self.client.get("/api/contacts").json["total"], 1)

    def test_demo_seed_is_explicit_and_does_not_overwrite_data(self):
        runner = self.app.test_cli_runner()
        self.assertEqual(runner.invoke(args=["seed-demo"]).exit_code, 0)
        self.assertEqual(self.client.get("/api/contacts").json["total"], 5)
        second = runner.invoke(args=["seed-demo"])
        self.assertIn("Added 0", second.output)
        self.assertEqual(self.client.get("/api/contacts").json["total"], 5)

    def test_repeated_create_returns_conflict_without_duplicate_record(self):
        first = self.write("POST", "/api/contacts", VALID_CONTACT)
        second = self.write("POST", "/api/contacts", VALID_CONTACT)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json["error"], "This contact already exists.")
        self.assertEqual(self.client.get("/api/contacts").json["total"], 1)

    def test_malformed_requests_and_unsupported_methods_are_json_errors(self):
        malformed = self.client.post(
            "/api/contacts", data="{not json", content_type="application/json",
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.mimetype, "application/json")
        self.assertEqual(self.client.post(
            "/api/contacts", json=[], headers={"X-CSRF-Token": self.csrf},
        ).status_code, 422)
        unsupported = self.client.patch("/api/contacts", json=VALID_CONTACT, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(unsupported.status_code, 405)
        self.assertEqual(unsupported.mimetype, "application/json")
        self.assertEqual(self.client.get("/api/contacts/CH-9999").status_code, 404)
        self.assertEqual(self.client.get("/api/contacts").json["total"], 0)

    def test_sql_injection_like_search_remains_literal(self):
        self.assertEqual(self.write("POST", "/api/contacts", VALID_CONTACT).status_code, 201)
        result = self.client.get("/api/contacts", query_string={"search": "' OR 1=1 --"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["contacts"], [])
        self.assertEqual(result.json["total"], 1)

    def test_database_connection_error_returns_generic_json(self):
        broken = create_app({
            "TESTING": True,
            "DATABASE": self.temp_dir.name,
            "SECRET_KEY": "test-only-secret",
            "ADMIN_PASSWORD_HASH": generate_password_hash("testing-password-123"),
        })
        with self.assertLogs(broken.logger, level="ERROR"):
            response = broken.test_client().get("/api/contacts")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, "application/json")
        self.assertNotIn(self.temp_dir.name, response.get_data(as_text=True))
        self.assertNotIn("Traceback", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
