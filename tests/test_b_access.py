"""
router access regression checks, isolated from real DB and app.main.

pytest starts each scenario in a fresh Python process so previously imported
settings/engines cannot leak across tests. Direct execution runs all scenarios.
This harness provides test-only sessions and APIError HTTP rendering.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCENARIOS = (
    "test_anonymous_list_detail_and_history_return_401",
    "test_other_owner_detail_and_history_return_404",
    "test_other_owner_list_excludes_foreign_conversation",
    "test_owner_can_read_list_detail_and_history",
    "test_logout_same_client_then_access_returns_401",
)


def register_test_error_handler(app):
    # app.main is intentionally an unintegrated foundation in this B branch.
    # Use the REAL APIError type, with an explicitly TEST-ONLY renderer.
    # This checks status decisions, not the final production error envelope.
    from fastapi.responses import JSONResponse
    from app.errors import APIError

    @app.exception_handler(APIError)
    async def render_api_error(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )


def run_access_checks(scenario=None):
    class BAccessTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            # Keep imports inside the guarded setup: settings must not be cached
            # before the temporary DATABASE_URL is installed.
            if any(name in sys.modules for name in ("app.config", "app.database")):
                raise RuntimeError("별도 Python 프로세스로 실행하세요. 설정이 이미 로드되었습니다.")
            cls.folder = tempfile.TemporaryDirectory(prefix="b-access-test-")
            cls.addClassCleanup(cls.folder.cleanup)
            cls.db_path = Path(cls.folder.name) / "isolated.sqlite3"
            env = patch.dict(os.environ, {
                "DATABASE_URL": "sqlite:///" + cls.db_path.as_posix(),
                "SECRET_KEY": "b-access-test-only-secret-at-least-32-characters",
                "LLM_API_KEY": "",
            })
            env.start()
            cls.addClassCleanup(env.stop)

            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from sqlalchemy.orm import Session
            from starlette.middleware.sessions import SessionMiddleware
            from app.database import Base, engine, get_db
            from app.models.user import User
            from app.models.shortform import Conversation, ConversationTurn
            from app.routers.auth import router as auth_router
            from app.routers.conversations import router as conversations_router
            from app.security import hash_password
            from app.services.shortform.schemas import Brief

            cls.addClassCleanup(engine.dispose)
            # Check before ANY table creation/session write. Never fall back to the
            # app's default DB if the real settings ignore our environment variable.
            if engine.url.get_backend_name() != "sqlite":
                raise RuntimeError("테스트 DB가 SQLite가 아닙니다. 중단합니다.")
            if not engine.url.database or Path(engine.url.database).resolve() != cls.db_path.resolve():
                raise RuntimeError("임시 DB 설정이 반영되지 않았습니다. 실제 DB에 접근하지 않습니다.")

            app = FastAPI()
            register_test_error_handler(app)
            app.add_middleware(
                SessionMiddleware,
                secret_key="b-access-test-only-secret-at-least-32-characters",
                https_only=False,  # In-process TestClient only, not deployment policy.
            )
            app.include_router(auth_router)
            app.include_router(conversations_router)

            def test_db():
                with Session(engine) as db:
                    yield db

            app.dependency_overrides[get_db] = test_db
            Base.metadata.create_all(engine)
            cls.password = "B-access-test-password-1234"
            with Session(engine) as db:
                owner = User(email="b-owner@example.com", password_hash=hash_password(cls.password))
                outsider = User(email="b-outsider@example.com", password_hash=hash_password(cls.password))
                db.add_all([owner, outsider])
                db.flush()
                conv = Conversation(user_id=owner.id, title="owner-only", brief_json=Brief().model_dump_json())
                db.add(conv)
                db.flush()
                cls.conversation_id = conv.id
                db.add(ConversationTurn(
                    conversation_id=conv.id, user_id=owner.id,
                    request_id="b-access-test-history", action="message",
                    question="owner-only-question", answer="owner-only-answer", status="success",
                ))
                db.commit()
            cls.app = app
            cls.TestClient = TestClient

        def setUp(self):
            # Fresh cookie jar per test; logout test deliberately keeps this same client.
            self.client = self.TestClient(self.app)
            self.client.__enter__()
            self.addCleanup(self.client.__exit__, None, None, None)

        def login(self, email="b-owner@example.com"):
            response = self.client.post("/api/auth/login", json={
                "email": email, "password": self.password,
            })
            self.assertEqual(response.status_code, 200, response.text)

        def protected_urls(self):
            return (
                "/api/conversations",
                f"/api/conversations/{self.conversation_id}",
                f"/api/me/chats?conversation_id={self.conversation_id}",
            )

        def test_anonymous_list_detail_and_history_return_401(self):
            for url in self.protected_urls():
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 401, response.text)

        def test_other_owner_detail_and_history_return_404(self):
            self.login("b-outsider@example.com")
            for url in self.protected_urls()[1:]:
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 404, response.text)
                    self.assertNotIn("owner-only", response.text)

        def test_other_owner_list_excludes_foreign_conversation(self):
            self.login("b-outsider@example.com")
            response = self.client.get("/api/conversations")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["items"], [])

        def test_owner_can_read_list_detail_and_history(self):
            # Positive controls prevent all-deny implementations from passing.
            self.login()
            listing, detail, history = [self.client.get(url) for url in self.protected_urls()]
            for response in (listing, detail, history):
                self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([x["conversation_id"] for x in listing.json()["items"]], [self.conversation_id])
            self.assertEqual(detail.json()["conversation_id"], self.conversation_id)
            self.assertEqual(history.json()["items"][0]["question"], "owner-only-question")

        def test_logout_same_client_then_access_returns_401(self):
            self.login()
            before = self.client.get(self.protected_urls()[1])
            self.assertEqual(before.status_code, 200, before.text)
            response = self.client.post("/api/auth/logout")
            self.assertEqual(response.status_code, 204, response.text)
            for url in self.protected_urls():
                with self.subTest(url=url):
                    after = self.client.get(url)
                    self.assertEqual(after.status_code, 401, after.text)
            # No manual cookie clearing and no new client after logout.

    loader = unittest.TestLoader()
    suite = (loader.loadTestsFromName(scenario, BAccessTests) if scenario
             else loader.loadTestsFromTestCase(BAccessTests))
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    scenario = sys.argv[1] if len(sys.argv) > 1 else None
    if scenario is not None and scenario not in SCENARIOS:
        raise SystemExit("Unknown access-test scenario")
    raise SystemExit(0 if run_access_checks(scenario) else 1)
else:
    import pytest

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_b_access_in_fresh_process(scenario):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), scenario],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr