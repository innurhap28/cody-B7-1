"""B: new tables leave existing users/chats and historical data intact."""
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Conversation(Base):
    __tablename__ = "reels_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    phase: Mapped[str] = mapped_column(String(20), default="briefing")
    brief_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(default=0)
    active_request_id: Mapped[str | None] = mapped_column(String(36))
    active_until: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class ConversationTurn(Base):
    __tablename__ = "reels_turns"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("reels_conversations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    action: Mapped[str] = mapped_column(String(20))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="processing")
    error_code: Mapped[str | None] = mapped_column(String(40))
    response_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ScriptVersion(Base):
    __tablename__ = "reels_scripts"
    __table_args__ = (UniqueConstraint("conversation_id", "revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("reels_conversations.id"), index=True)
    turn_id: Mapped[int] = mapped_column(ForeignKey("reels_turns.id"), unique=True)
    revision: Mapped[int]
    parent_script_id: Mapped[int | None] = mapped_column(ForeignKey("reels_scripts.id"))
    brief_json: Mapped[str] = mapped_column(Text)
    content_json: Mapped[str] = mapped_column(Text)
    references_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
