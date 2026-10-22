"""Shared foundation. C connects the integrated routes after A and B merge."""
from fastapi import FastAPI
from app.config import settings

app = FastAPI(title="인스타 릴스 대본 코치",
              docs_url="/docs" if settings.ENABLE_API_DOCS else None,
              redoc_url=None,
              openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None)


@app.get("/")
def home():
    return {"service": "STORY / REELS"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "shortform-coach"}
