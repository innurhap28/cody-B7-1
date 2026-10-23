"""Exercise the real app.main in isolated processes, without an AI key or real DB."""
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
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
    "test_a_pages_and_static_assets_are_connected",
    "test_chat_access_and_validation_do_not_call_ai",
    "test_chat_brief_generate_acknowledge_and_revise_are_saved",
    "test_chat_context_isolated_between_conversations",
    "test_ai_failures_preserve_brief_and_release_processing",
    "test_chat_database_failure_is_recorded_safely",
    "test_stale_chat_version_is_rejected_before_ai",
    "test_chat_logs_correlate_without_message_or_key",
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

        def new_conversation(self):
            payload, _ = self.create_account(self.client)
            self.login(self.client, payload)
            return self.add_conversation()

        def add_conversation(self):
            response = self.client.post("/api/conversations", json={})
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()

        def chat(self, conversation, message="아침 메뉴", action="message", script_id=None):
            body = {"conversation_id": conversation["conversation_id"],
                    "expected_version": conversation["version"], "action": action, "message": message}
            if script_id is not None:
                body["base_script_id"] = script_id
            return self.client.post("/api/chat", json=body)

        def complete_brief(self):
            return {"topic": "아침 메뉴", "goal": "정보 전달",
                    "audience": {"segment": "자취생", "age_range": "20대"},
                    "duration_sec": 30, "presentation_mode": "hands_only",
                    "direction_style": "차분한 실습", "core_message": "아침을 간단히 준비해요"}

        def script(self, title="아침의 한 장면"):
            return {"title": title, "duration_sec": 30,
                    "structure": {"name": "결과와 과정", "reason": "핵심 과정을 보여줍니다."},
                    "scenes": [{"scene_no": 1, "start_sec": 0, "end_sec": 30,
                                "purpose": "과정", "visual": "손으로 재료를 꺼낸다",
                                "dialogue": "아침을 준비해요", "caption": "간단한 한 끼",
                                "direction": "손과 재료를 고정 구도로 촬영"}],
                    "rationale": [{"scene_nos": [1], "card_ids": ["mp-intent"],
                                   "explanation": "장면을 중심 메시지에 맞춥니다."}]}

        def test_a_pages_and_static_assets_are_connected(self):
            response = self.client.get("/", follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/login")
            for action in ("login", "signup"):
                page = self.client.get("/" + action)
                self.assertEqual(page.status_code, 200)
                self.assertIn(f'data-action="{action}"', page.text)
            for path in ("css/shortform.css", "js/auth.js", "js/common.js", "js/shortform.js"):
                self.assertEqual(self.client.get("/static/" + path).status_code, 200)
            account, _ = self.create_account(self.client)
            self.login(self.client, account)
            page = self.client.get("/")
            self.assertEqual(page.status_code, 200)
            for marker in ('id="chat-form"', 'id="generate"', 'id="revise"', account["email"]):
                self.assertIn(marker, page.text)
            for path in ("/login", "/signup", "/history"):
                self.assertEqual(self.client.get(path, follow_redirects=False).headers["location"], "/")

        def test_chat_access_and_validation_do_not_call_ai(self):
            with patch("app.services.llm.ask_llm", new_callable=AsyncMock) as ask:
                self.assert_error(self.chat({"conversation_id": 1, "version": 0}), 401, "LOGIN_REQUIRED")
                conversation = self.new_conversation()
                self.assert_error(self.chat(conversation, message=" "), 422, "INVALID_INPUT")
                outsider, _ = self.create_account(self.client)
                self.login(self.client, outsider)
                self.assert_error(self.chat(conversation), 404, "NOT_FOUND")
                ask.assert_not_awaited()

        def test_chat_brief_generate_acknowledge_and_revise_are_saved(self):
            conversation = self.new_conversation()
            outputs = [
                {"brief_patch": {"topic": "아침 메뉴"}},
                {"brief_patch": self.complete_brief()},
                self.script(), {"brief_patch": {}}, self.script("행동으로 시작하는 아침"),
            ]
            with patch("app.services.llm.ask_llm", new=AsyncMock(
                    side_effect=[json.dumps(item, ensure_ascii=False) for item in outputs])) as ask:
                response = self.chat(conversation)
                self.assertEqual(response.status_code, 200, response.text)
                first = response.json()
                self.assertEqual(first["phase"], "briefing")
                self.assertLessEqual(len(first["follow_up_questions"]), 2)
                blocked = self.chat(first, action="generate")
                self.assertEqual(blocked.status_code, 200)
                self.assertEqual(blocked.json()["phase"], "briefing")
                self.assertEqual(ask.await_count, 1)
                response = self.chat(blocked.json(), message="20대 자취생에게 손만 촬영해 설명할게요")
                ready = response.json()
                self.assertEqual(ready["phase"], "ready")
                self.assertFalse(ready["brief"]["confirmed"])
                response = self.chat(ready, action="generate")
                self.assertEqual(response.status_code, 200, response.text)
                drafted = response.json()
                self.assertEqual(drafted["phase"], "drafted")
                self.assertTrue(drafted["brief"]["confirmed"])
                self.assertEqual(drafted["script"]["revision"], 1)
                self.assertEqual(drafted["references"][0]["card_id"], "mp-intent")
                self.assertEqual(drafted["request_id"], response.headers["X-Request-ID"])
                ack = self.chat(drafted, message="고마워").json()
                self.assertEqual(ack["phase"], "drafted")
                self.assertTrue(ack["brief"]["confirmed"])
                current = self.client.get(f'/api/conversations/{conversation["conversation_id"]}').json()
                self.assertEqual(current["latest_script"]["script_id"], drafted["script"]["script_id"])
                response = self.chat(current, action="revise", message="첫 장면을 행동으로 바꿔줘",
                                     script_id=current["latest_script"]["script_id"])
                self.assertEqual(response.status_code, 200, response.text)
                revised = response.json()
                self.assertEqual(revised["script"]["revision"], 2)
                self.assertEqual(revised["script"]["parent_script_id"], drafted["script"]["script_id"])
            history = self.client.get(f'/api/me/chats?conversation_id={conversation["conversation_id"]}').json()["items"]
            self.assertEqual(len(history), 6)
            self.assertTrue(all(t["status"] == "success" and t["question"] and t["created_at"] for t in history))
            self.assertEqual(history[0]["response"]["script"]["revision"], 2)

        def test_chat_context_isolated_between_conversations(self):
            first = self.new_conversation()
            mock = AsyncMock(return_value=json.dumps({"brief_patch": {"topic": "첫방전용주제"}}))
            with patch("app.services.llm.ask_llm", new=mock):
                self.assertEqual(self.chat(first).status_code, 200)
            second = self.add_conversation()
            with patch("app.services.llm.ask_llm", new=AsyncMock(return_value='{"brief_patch":{}}')) as ask:
                self.assertEqual(self.chat(second, message="새 기획").status_code, 200)
            messages = ask.await_args.args[1]
            self.assertNotIn("첫방전용주제", json.dumps(messages, ensure_ascii=False))
            self.assertEqual(len(messages), 2)

        def test_ai_failures_preserve_brief_and_release_processing(self):
            from app.services import llm
            conversation = self.new_conversation()
            with patch("app.services.llm.ask_llm", new=AsyncMock(
                    return_value=json.dumps({"brief_patch": self.complete_brief()}))):
                ready = self.chat(conversation).json()
            with patch("app.services.llm.ask_llm", new=AsyncMock(return_value=json.dumps(self.script()))):
                drafted_response = self.chat(ready, action="generate")
                self.assertEqual(drafted_response.status_code, 200, drafted_response.text)
                drafted = drafted_response.json()
            cases = [(llm.AITimeoutError(), 504, "AI_TIMEOUT"),
                     (llm.AIAuthenticationError(), 502, "AI_AUTH_ERROR"),
                     (llm.AIAccessDeniedError(), 502, "AI_ACCESS_DENIED"),
                     (llm.AIRateLimitError(), 429, "AI_RATE_LIMIT"),
                     (llm.AIServiceError(), 502, "AI_ERROR"),
                     (None, 502, "AI_INVALID_RESPONSE")]
            for failure, status, code in cases:
                with self.subTest(code=code), patch("app.services.llm.ask_llm", new=AsyncMock(
                        side_effect=failure, return_value="not-json")):
                    self.assert_error(self.chat(drafted, action="revise", message="첫 장면을 바꿔줘",
                                                script_id=drafted["script"]["script_id"]), status, code)
                current = self.client.get(f'/api/conversations/{conversation["conversation_id"]}').json()
                self.assertEqual(current["version"], drafted["version"])
                self.assertEqual(current["brief"], drafted["brief"])
                self.assertEqual(current["phase"], "drafted")
                self.assertEqual(current["latest_script"]["script_id"], drafted["script"]["script_id"])
                self.assertFalse(current["processing"])
            history = self.client.get(f'/api/me/chats?conversation_id={conversation["conversation_id"]}').json()["items"]
            self.assertEqual(len([t for t in history if t["status"] in ("error", "timeout")]), len(cases))
            with patch("app.services.llm.ask_llm", new=AsyncMock(return_value='{"brief_patch":{}}')) as ask:
                self.assertEqual(self.chat(drafted, message="계속해줘").status_code, 200)
                # Failed turns do not become previous question/answer context.
                self.assertEqual(len(ask.await_args.args[1]), 6)

        def test_chat_database_failure_is_recorded_safely(self):
            from sqlalchemy.exc import SQLAlchemyError
            conversation = self.new_conversation()
            with patch("app.services.llm.ask_llm", new=AsyncMock(return_value='{"brief_patch":{}}')), \
                    patch("app.routers.shortform.store.complete_turn",
                          side_effect=SQLAlchemyError("private database body")):
                response = self.chat(conversation)
            self.assert_error(response, 503, "DB_ERROR")
            self.assertNotIn("private database", response.text)
            current = self.client.get(f'/api/conversations/{conversation["conversation_id"]}').json()
            self.assertFalse(current["processing"])
            self.assertEqual(current["version"], 0)
            history = self.client.get(f'/api/me/chats?conversation_id={conversation["conversation_id"]}').json()["items"]
            self.assertEqual(history[0]["error_code"], "DB_ERROR")

        def test_stale_chat_version_is_rejected_before_ai(self):
            conversation = self.new_conversation()
            with patch("app.services.llm.ask_llm", new=AsyncMock(return_value='{"brief_patch":{}}')):
                self.assertEqual(self.chat(conversation).status_code, 200)
            with patch("app.services.llm.ask_llm", new_callable=AsyncMock) as ask:
                self.assert_error(self.chat(conversation), 409, "CONVERSATION_CONFLICT")
                ask.assert_not_awaited()

        def test_chat_logs_correlate_without_message_or_key(self):
            conversation = self.new_conversation()
            with self.assertLogs(level="INFO") as records, patch("app.services.llm.ask_llm", new=AsyncMock(
                    return_value='{"brief_patch":{}}')):
                response = self.chat(conversation, message="private-user-input-example")
            self.assertEqual(response.status_code, 200, response.text)
            request_id = response.json()["request_id"]
            logged = "\n".join(records.output)
            for event in ("request_received", "ai_call_start", "ai_call_success", "db_save_success"):
                self.assertTrue(any(event in line and request_id in line for line in records.output))
            self.assertNotIn("private-user-input-example", logged)
            self.assertNotIn("main-access-test-only-signing-secret", logged)

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
