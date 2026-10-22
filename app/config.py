from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """.env 파일 또는 환경 변수에서 읽는 앱 설정."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # B: 세션 서명·SQLite 연결
    SECRET_KEY: str = Field(min_length=16)
    DATABASE_URL: str = "sqlite:///./app.db"

    # C: Codyssey 서버 전용 API
    LLM_API_KEY: str = ""
    LLM_API_STYLE: Literal["anthropic", "openai"] = "anthropic"
    # Codyssey alias; the live response on 2026-10-20 identified Sonnet 4.6.
    LLM_MODEL: str = "claude-sonnet-4"
    LLM_BASE_URL: str = "https://copa.codyssey.kr/v1"
    LLM_TIMEOUT_SECONDS: float = Field(default=90, gt=0)
    LLM_MAX_COMPLETION_TOKENS: int = Field(default=8000, ge=128, le=16000)

    LLM_JSON_MODE: bool = False

    # Shortform: 교육용 NC 자료는 상업용 scope에서 검색되지 않는다.
    KNOWLEDGE_USAGE_SCOPE: str = "educational_noncommercial"
    SESSION_HTTPS_ONLY: bool = False
    ENABLE_API_DOCS: bool = False
    CHAT_TOTAL_TIMEOUT_SECONDS: float = Field(default=105, gt=0, le=120)


settings = Settings()
