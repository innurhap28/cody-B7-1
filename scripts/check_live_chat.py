"""Opt-in live Codyssey smoke check using the real app and an isolated local DB.

Makes up to four real AI calls. Never prints credentials or overwrites app.db.
Local evidence, generated script and the synthetic account remain under tmp/.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize up to four external AI calls")
    args = parser.parse_args()
    if not args.live:
        parser.error("Actual AI requests require --live; unit tests do not need it.")

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.chdir(root)
    temp_root = root / "tmp"
    temp_root.mkdir(exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="live-chat-", dir=temp_root)).resolve()
    os.environ["DATABASE_URL"] = "sqlite:///" + (evidence / "app.db").as_posix()
    os.environ["SESSION_HTTPS_ONLY"] = "false"  # TestClient uses local HTTP.

    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import settings
    from app.database import engine

    if not settings.LLM_API_KEY.strip():
        print("LLM_API_KEY is missing. Configure the local .env; no AI call made.")
        return 1
    if Path(engine.url.database).resolve() != evidence / "app.db":
        raise RuntimeError("Refusing to access a non-isolated database")

    # Keep console output limited to sanitized stage summaries.
    for name in ("httpx", "app.main", "app.routers.auth", "app.services.accounts",
                 "app.services.shortform.store", "app.routers.shortform"):
        logging.getLogger(name).setLevel(logging.WARNING)
    report = {"mode": "real_app_real_provider_isolated_db", "model_requested": settings.LLM_MODEL,
              "api_style": settings.LLM_API_STYLE, "stages": [], "result": "running"}
    report_path = evidence / "report.json"

    def save():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def checked(response, status, stage, started=None):
        entry = {"stage": stage, "status": response.status_code,
                 "request_id": response.headers.get("X-Request-ID")}
        if started is not None:
            entry["elapsed_seconds"] = round(time.monotonic() - started, 2)
        if response.status_code != status:
            try:
                data = response.json()
            except ValueError:
                data = {}
            entry["error"] = data.get("error", "UNEXPECTED_HTTP_STATUS")
            report["stages"].append(entry)
            save()
            raise RuntimeError(f"{stage} failed: HTTP {response.status_code}, {entry['error']}")
        report["stages"].append(entry)
        save()
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        return response

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            checked(client.get("/login"), 200, "login_page")
            account = {"email": f"live-{uuid.uuid4().hex}@example.com",
                       "password": secrets.token_urlsafe(24)}
            checked(client.post("/api/auth/signup", json=account), 201, "signup")
            checked(client.post("/api/auth/login", json=account), 200, "login")
            checked(client.get("/"), 200, "workspace")
            conversation = checked(client.post("/api/conversations", json={}), 201,
                                   "create_conversation").json()
            cid = conversation["conversation_id"]

            def chat(state, stage, message, action="message", script_id=None):
                payload = {"conversation_id": cid, "expected_version": state["version"],
                           "action": action, "message": message}
                if script_id is not None:
                    payload["base_script_id"] = script_id
                print(f"Starting real AI stage: {stage}", flush=True)
                started = time.monotonic()
                result = checked(client.post("/api/chat", json=payload), 200, stage, started).json()
                (evidence / f"{stage}.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                return result

            first = chat(conversation, "briefing", "20대 자취생을 위한 30초 아침 메뉴 릴스를 만들고 싶어요.")
            if first["phase"] != "briefing" or not 1 <= len(first["follow_up_questions"]) <= 2:
                raise RuntimeError("Expected one or two missing-condition questions")
            ready = chat(first, "brief_summary",
                         "주제는 아침 메뉴, 목적은 간단한 조리 방법의 정보 전달입니다. "
                         "시청자는 요리 초보인 20대 자취생, 길이는 30초입니다. "
                         "인물과 얼굴은 나오지 않고 손만 촬영합니다. 등장인물은 없습니다. "
                         "차분하고 친근한 실습 연출과 말투를 원해요. "
                         "핵심 메시지는 적은 재료로도 간단한 아침을 준비할 수 있다는 것입니다. "
                         "집 주방에서 휴대폰 한 대로 촬영하고, 제약은 없습니다.")
            if ready["phase"] != "ready" or ready["brief"]["confirmed"]:
                raise RuntimeError("Expected a complete unconfirmed brief; inspect saved evidence")
            drafted = chat(ready, "generation", "이 조건을 확인했어요. 대본을 작성해 주세요.", action="generate")
            if drafted["phase"] != "drafted" or not drafted["script"] or not drafted["references"]:
                raise RuntimeError("Expected a saved draft with actual retrieved references")
            if (drafted["script"]["scenes"][0]["start_sec"] != 0
                    or drafted["script"]["scenes"][-1]["end_sec"] != 30):
                raise RuntimeError("Expected a complete 30-second timeline")
            revised = chat(drafted, "revision", "첫 장면을 설명 대신 재료를 꺼내는 행동으로 시작해 주세요.",
                           action="revise", script_id=drafted["script"]["script_id"])
            if (revised["script"]["revision"] != 2
                    or revised["script"]["parent_script_id"] != drafted["script"]["script_id"]):
                raise RuntimeError("Expected a second saved script revision")
            detail = checked(client.get(f"/api/conversations/{cid}"), 200, "read_conversation").json()
            history = checked(client.get(f"/api/me/chats?conversation_id={cid}"), 200, "read_history").json()
            if detail["latest_script"]["script_id"] != revised["script"]["script_id"]:
                raise RuntimeError("Latest script not persisted")
            if len(history["items"]) != 4 or any(t["status"] != "success" for t in history["items"]):
                raise RuntimeError("Expected four persisted successful turns")
            checked(client.post("/api/auth/logout"), 204, "logout")
            checked(client.get(f"/api/conversations/{cid}"), 401, "access_after_logout")
            report.update(result="passed", real_chat_requests=4, saved_turns=4,
                          script_revisions=2, source_cards=[r["card_id"] for r in revised["references"]])
    except Exception as exc:
        report.update(result="failed", failure_type=type(exc).__name__)
        # No traceback or provider body: only controlled stage failures are printed.
        print(f"Live check failed ({type(exc).__name__}); inspect sanitized report.", flush=True)
    finally:
        save()
        engine.dispose()
        print(f"Evidence: {evidence}", flush=True)
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
