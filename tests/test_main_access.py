"""Exercise the real app.main in isolated processes, without an AI key or real DB."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid


SCENARIOS = (
    "test_startup_creates_tables_in_temporary_database",
    "test_anonymous_protected_routes_return_401",
    "test_signup_login_sets_session_and_allows_access",
    "test_invalid_credentials_return_401_without_session",
    "test_invalid_signup_returns_safe_422",
    "test_foreign_conversations_and_history_are_hidden",
    "test_logout_same_client_revokes_normal_access",
    "test_database_failure_returns_safe_503",
)


def run_checks(scenario=None):
    class MainAccessTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            if any(name in sys.modules for name in ("app.config", "app.database", "app.main")):
                raise RuntimeError("Run this integration suite in a fresh process.")
            cls.folder = tempfile.TemporaryDirectory(
                prefix="main-access-", dir=os.environ.get("SHORTFORM_TEST_TMPDIR"))
            cls.addClassCleanup(cls.folder.cleanup)
            cls.db_path = Path(cls.folder.name).resolve() / "test.sqlite3"
            env = patch.dict(os.environ, {
                "SECRET_KEY": "main-access-test-only-signing-secret-at-least-32",
                "DATABASE_URL": "sqlite:///" + cls.db_path.as_posix(),
                "LLM_API_KEY": "",
                "SESSION_HTTPS_ONLY": "false",
            })
            env.start()
            cls.addClassCleanup(env.stop)
            # Import the production entry point. No substitute app, dependency
            # override, test-only middleware or manually created tables.
            from app.main import app
            from app.database import engine
            from fastapi.testclient import TestClient
            cls.app, cls.engine, cls.client_type = app, engine, TestClient
            cls.addClassCleanup(engine.dispose)
            if Path(engine.url.database).resolve() != cls.db_path:
                raise RuntimeError("Refusing to access a non-test database.")

        def setUp(self):
            self.client = self.client_type(self.app, raise_server_exceptions=False)
            self.client.__enter__()  # Real lifespan must create the database.
            self.addCleanup(self.client.__exit__, None, None, None)

        def create_account(self, client):
            email = f"integration-{uuid.uuid4().hex}@example.com"
            payload = {"email": email, "password": "Integration-password-1234"}
            response = client.post("/api/auth/signup", json=payload)
            self.assertEqual(response.status_code, 201, response.text)
            return payload, response.json()["id"]

        def login(self, client, payload):
            response = client.post("/api/auth/login", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            return response

        def assert_error(self, response, status, code):
            self.assertEqual(response.status_code, status, response.text)
            data = response.json()
            self.assertEqual(data["error"], code)
            self.assertTrue(data["message"])
            self.assertEqual(data["request_id"], response.headers["X-Request-ID"])
            uuid.UUID(data["request_id"])

        def test_startup_creates_tables_in_temporary_database(self):
            from sqlalchemy import inspect
            self.assertTrue(self.db_path.is_file())
            self.assertTrue({"users", "reels_conversations", "reels_turns", "reels_scripts"}
                            <= set(inspect(self.engine).get_table_names()))
            self.assertEqual(self.client.get("/health").json()["status"], "ok")

        def test_anonymous_protected_routes_return_401(self):
            for url in ("/api/me", "/api/conversations", "/api/conversations/1",
                        "/api/me/chats?conversation_id=1"):
                with self.subTest(url=url):
                    self.assert_error(self.client.get(url), 401, "LOGIN_REQUIRED")

        def test_signup_login_sets_session_and_allows_access(self):
            payload, user_id = self.create_account(self.client)
            self.assertEqual(self.client.get("/api/me").status_code, 401)
            response = self.login(self.client, payload)
            cookie = response.headers["set-cookie"].lower()
            for attribute in ("httponly", "samesite=lax", "max-age=28800"):
                self.assertIn(attribute, cookie)
            me = self.client.get("/api/me")
            self.assertEqual(me.status_code, 200, me.text)
            self.assertEqual(me.json()["id"], user_id)
            self.assertFalse(me.json()["ai_configured"])
            self.assertEqual(self.client.get("/api/conversations").status_code, 200)

        def test_invalid_credentials_return_401_without_session(self):
            payload, _ = self.create_account(self.client)
            response = self.client.post("/api/auth/login", json={**payload, "password": "wrong-password"})
            self.assert_error(response, 401, "INVALID_CREDENTIALS")
            self.assert_error(self.client.get("/api/me"), 401, "LOGIN_REQUIRED")

        def test_invalid_signup_returns_safe_422(self):
            secret = "bad"
            response = self.client.post("/api/auth/signup", json={"email": "invalid", "password": secret})
            self.assert_error(response, 422, "INVALID_INPUT")
            self.assertNotIn('"input"', response.text)
            self.assertNotIn(secret, response.text)

        def test_foreign_conversations_and_history_are_hidden(self):
            from sqlalchemy.orm import Session
            from app.models.shortform import ConversationTurn
            owner, owner_id = self.create_account(self.client)
            self.login(self.client, owner)
            response = self.client.post("/api/conversations", json={"title": "owner-private"})
            self.assertEqual(response.status_code, 201, response.text)
            conversation_id = response.json()["conversation_id"]
            with Session(self.engine) as db:
                db.add(ConversationTurn(conversation_id=conversation_id, user_id=owner_id,
                       request_id=str(uuid.uuid4()), action="message", question="private-question",
                       answer="private-answer", status="success"))
                db.commit()
            detail = f"/api/conversations/{conversation_id}"
            history = f"/api/me/chats?conversation_id={conversation_id}"
            self.assertEqual(self.client.get(detail).status_code, 200)
            self.assertEqual(self.client.get(history).json()["items"][0]["question"], "private-question")
            with self.client_type(self.app, raise_server_exceptions=False) as outsider:
                payload, _ = self.create_account(outsider)
                self.login(outsider, payload)
                self.assertEqual(outsider.get("/api/conversations").json()["items"], [])
                for url in (detail, history):
                    response = outsider.get(url)
                    self.assert_error(response, 404, "NOT_FOUND")
                    self.assertNotIn("private", response.text)

        def test_logout_same_client_revokes_normal_access(self):
            payload, _ = self.create_account(self.client)
            self.login(self.client, payload)
            self.assertEqual(self.client.get("/api/me").status_code, 200)
            self.assertEqual(self.client.post("/api/auth/logout").status_code, 204)
            self.assert_error(self.client.get("/api/me"), 401, "LOGIN_REQUIRED")
            self.assert_error(self.client.get("/api/conversations"), 401, "LOGIN_REQUIRED")

        def test_database_failure_returns_safe_503(self):
            from sqlalchemy.exc import SQLAlchemyError
            with patch("app.routers.auth.AccountService.authenticate",
                       side_effect=SQLAlchemyError("private database details")):
                response = self.client.post("/api/auth/login", json={
                    "email": "test@example.com", "password": "Example-password-1234"})
            self.assert_error(response, 503, "DB_ERROR")
            self.assertNotIn("private database", response.text)

    loader = unittest.TestLoader()
    suite = (loader.loadTestsFromName(scenario, MainAccessTests) if scenario
             else loader.loadTestsFromTestCase(MainAccessTests))
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    scenario = sys.argv[1] if len(sys.argv) > 1 else None
    if scenario is not None and scenario not in SCENARIOS:
        raise SystemExit("Unknown test scenario")
    raise SystemExit(0 if run_checks(scenario) else 1)
else:
    import pytest

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_real_main_in_fresh_process(scenario):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), scenario],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
