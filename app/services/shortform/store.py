"""B: ownership, short SQLite transactions and a durable per-conversation lease."""
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.errors import APIError
from app.models.shortform import Conversation, ScriptVersion, ConversationTurn
from app.services.shortform.schemas import Brief, ChatRequest

logger = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def timestamp(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def owned(db: Session, user_id: int, conversation_id: int) -> Conversation:
    item = db.scalar(select(Conversation).where(Conversation.id == conversation_id,
                                               Conversation.user_id == user_id))
    if item is None:
        raise APIError(404, "NOT_FOUND", "대화방을 찾을 수 없습니다.")
    return item


def script_payload(script: ScriptVersion | None) -> dict | None:
    if script is None:
        return None
    return {**json.loads(script.content_json), "script_id": script.id, "revision": script.revision,
            "parent_script_id": script.parent_script_id, "references": json.loads(script.references_json)}


def latest_script(db: Session, conversation_id: int) -> ScriptVersion | None:
    return db.scalar(select(ScriptVersion).where(ScriptVersion.conversation_id == conversation_id)
                     .order_by(ScriptVersion.revision.desc()).limit(1))


def conversation_payload(db: Session, item: Conversation) -> dict:
    return {"conversation_id": item.id, "title": item.title, "phase": item.phase,
            "version": item.version, "brief": json.loads(item.brief_json),
            "latest_script": script_payload(latest_script(db, item.id)),
            "processing": bool(item.active_request_id and item.active_until and item.active_until > now()),
            "created_at": timestamp(item.created_at), "updated_at": timestamp(item.updated_at)}


@dataclass
class TurnContext:
    turn_id: int
    conversation_id: int
    version: int
    phase: str
    brief: Brief
    history: list[dict]
    latest_script: dict | None


def begin_turn(db: Session, user_id: int, body: ChatRequest, request_id: str, lease_seconds: float) -> TurnContext:
    # Authentication performs a SELECT on this session. End that read transaction
    # before acquiring the lease. No write transaction remains during AI await.
    db.commit()
    clock = now()
    result = db.execute(update(Conversation).where(
        Conversation.id == body.conversation_id, Conversation.user_id == user_id,
        Conversation.version == body.expected_version,
        or_(Conversation.active_request_id.is_(None), Conversation.active_until <= clock),
    ).values(active_request_id=request_id, active_until=clock + timedelta(seconds=lease_seconds),
             updated_at=clock))
    if result.rowcount != 1:
        db.rollback()
        owned(db, user_id, body.conversation_id)
        db.rollback()
        raise APIError(409, "CONVERSATION_CONFLICT", "다른 요청이 처리 중이거나 기획이 변경되었습니다. 대화를 다시 불러와 주세요.")
    # Recover a request whose owner process died. A late completion cannot pass
    # complete_turn's active_request_id comparison after this point.
    db.execute(update(ConversationTurn).where(ConversationTurn.conversation_id == body.conversation_id,
                                      ConversationTurn.status == "processing")
               .values(status="error", error_code="REQUEST_EXPIRED"))
    item = owned(db, user_id, body.conversation_id)
    previous_script = script_payload(latest_script(db, item.id))
    if body.action == "revise" and (not previous_script or previous_script["script_id"] != body.base_script_id):
        db.rollback()
        raise APIError(409, "SCRIPT_CONFLICT", "현재 대본을 다시 불러온 뒤 수정해 주세요.")
    recent = db.scalars(select(ConversationTurn).where(ConversationTurn.conversation_id == item.id,
                                               ConversationTurn.user_id == user_id, ConversationTurn.status == "success")
                        .order_by(ConversationTurn.id.desc()).limit(5)).all()
    context_values = (item.id, item.version, item.phase, Brief.model_validate_json(item.brief_json),
                      [{"question": t.question, "answer": t.answer} for t in reversed(recent)], previous_script)
    turn = ConversationTurn(conversation_id=item.id, user_id=user_id, request_id=request_id,
                     action=body.action, question=body.message, status="processing")
    db.add(turn)
    db.flush()
    turn_id = turn.id
    db.commit()
    logger.info("db_save_success user_id=%s conversation_id=%s request_id=%s status=processing", user_id, body.conversation_id, request_id)
    return TurnContext(turn_id, *context_values)


def complete_turn(db: Session, context: TurnContext, request_id: str, payload: dict) -> dict:
    data = dict(payload)
    clock = now()
    result = db.execute(update(Conversation).where(
        Conversation.id == context.conversation_id, Conversation.version == context.version,
        Conversation.active_request_id == request_id, Conversation.active_until > clock,
    ).values(phase=data["phase"], brief_json=encode(data["brief"]), version=context.version + 1,
             active_request_id=None, active_until=None, updated_at=clock))
    if result.rowcount != 1:
        db.rollback()
        raise APIError(409, "REQUEST_EXPIRED", "기획 상태가 변경되어 결과를 저장하지 못했습니다. 대화를 다시 불러와 주세요.")
    conversation = db.get(Conversation, context.conversation_id)
    if conversation.title == "새 릴스 기획" and data["brief"].get("topic"):
        conversation.title = data["brief"]["topic"][:100]
    if data["script"] is not None:
        previous = context.latest_script
        script = ScriptVersion(conversation_id=context.conversation_id, turn_id=context.turn_id,
                             revision=(previous["revision"] + 1) if previous else 1,
                             parent_script_id=previous["script_id"] if previous else None,
                             brief_json=encode(data["brief"]), content_json=encode(data["script"]),
                             references_json=encode(data["references"]))
        db.add(script)
        db.flush()
        data["script"] = script_payload(script)
    data.update(chat_id=context.turn_id, conversation_id=context.conversation_id,
                version=context.version + 1, request_id=request_id)
    db.execute(update(ConversationTurn).where(ConversationTurn.id == context.turn_id, ConversationTurn.request_id == request_id,
                                      ConversationTurn.status == "processing")
               .values(answer=data["answer"], response_json=encode(data), status="success"))
    db.commit()
    logger.info("db_save_success conversation_id=%s chat_id=%s request_id=%s status=success", context.conversation_id, context.turn_id, request_id)
    return data


def fail_turn(db: Session, context: TurnContext, request_id: str, error_code: str) -> None:
    db.rollback()
    db.execute(update(Conversation).where(Conversation.id == context.conversation_id,
                                         Conversation.active_request_id == request_id)
               .values(active_request_id=None, active_until=None))
    db.execute(update(ConversationTurn).where(ConversationTurn.id == context.turn_id, ConversationTurn.request_id == request_id,
                                      ConversationTurn.status == "processing")
               .values(status="timeout" if error_code == "AI_TIMEOUT" else "error", error_code=error_code))
    db.commit()
    logger.info("db_save_success conversation_id=%s chat_id=%s request_id=%s status=failure_recorded", context.conversation_id, context.turn_id, request_id)
