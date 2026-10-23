"""B: signed-in account metadata and owner-scoped planning/history resources."""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_login
from app.models.shortform import Conversation, ConversationTurn
from app.services.shortform.schemas import Brief, ConversationCreate
from app.services.shortform import store

router = APIRouter(prefix="/api", tags=["planning-history"])
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("/me")
def me(user=Depends(require_login)):
    return {"id": user.id, "email": user.email, "ai_provider": "codyssey", "ai_configured": bool(settings.LLM_API_KEY)}


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationCreate, user=Depends(require_login), db: Session = Depends(get_db)):
    item = Conversation(user_id=user.id, title=body.title, brief_json=Brief().model_dump_json())
    db.add(item)
    db.commit()
    db.refresh(item)
    return store.conversation_payload(db, item)


@router.get("/conversations")
def conversations(limit: Limit = 20, offset: Annotated[int, Query(ge=0)] = 0,
                  user=Depends(require_login), db: Session = Depends(get_db)):
    rows = db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                      .order_by(Conversation.updated_at.desc(), Conversation.id.desc()).offset(offset).limit(limit)).all()
    return {"items": [store.conversation_payload(db, row) for row in rows], "limit": limit, "offset": offset}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: int, user=Depends(require_login), db: Session = Depends(get_db)):
    return store.conversation_payload(db, store.owned(db, user.id, conversation_id))


@router.get("/me/chats")
def history(conversation_id: int, limit: Limit = 20, offset: Annotated[int, Query(ge=0)] = 0,
            user=Depends(require_login), db: Session = Depends(get_db)):
    store.owned(db, user.id, conversation_id)
    rows = db.scalars(select(ConversationTurn).where(ConversationTurn.user_id == user.id,
                                             ConversationTurn.conversation_id == conversation_id)
                      .order_by(ConversationTurn.id.desc()).offset(offset).limit(limit)).all()
    return {"items": [{"chat_id": row.id, "question": row.question, "answer": row.answer,
                       "status": row.status, "error_code": row.error_code, "request_id": row.request_id,
                       "created_at": store.timestamp(row.created_at),
                       "response": json.loads(row.response_json) if row.response_json else None} for row in rows],
            "limit": limit, "offset": offset}
