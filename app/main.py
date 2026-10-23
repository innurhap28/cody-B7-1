
"""C integration: real B sessions, database lifecycle and safe API errors."""
from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401 -- register every table before create_all
from app.config import settings
from app.database import Base, engine
from app.errors import APIError
from app.routers import auth, conversations

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError:
        logger.error("db_init_fail")
        raise RuntimeError("데이터베이스 초기화에 실패했습니다. DB 경로와 권한을 확인해 주세요.") from None
    logger.info("db_init_success")
    yield


app = FastAPI(
    title="인스타 릴스 대본 코치",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=settings.SESSION_HTTPS_ONLY,
    max_age=8 * 60 * 60,
)


@app.middleware("http")
async def request_boundary(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    logger.info("request_received request_id=%s method=%s path=%s",
                request.state.request_id, request.method, request.url.path)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    return response


def error_response(request: Request, status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={
        "error": code, "message": message,
        "request_id": getattr(request.state, "request_id", None),
    })


@app.exception_handler(APIError)
async def api_error(request: Request, exc: APIError):
    return error_response(request, exc.status_code, exc.error, exc.message)


@app.exception_handler(RequestValidationError)
async def invalid_input(request: Request, exc: RequestValidationError):
    # Do not serialize validation details containing passwords or request input.
    return error_response(request, 422, "INVALID_INPUT", "입력 형식과 길이를 확인해 주세요.")


@app.exception_handler(SQLAlchemyError)
async def database_failure(request: Request, exc: SQLAlchemyError):
    logger.error("db_operation_fail request_id=%s method=%s path=%s",
                 request.state.request_id, request.method, request.url.path)
    return error_response(request, 503, "DB_ERROR", "데이터를 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.")


app.include_router(auth.router)
app.include_router(conversations.router)


@app.get("/")
def home():
    return {"service": "STORY / REELS"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "shortform-coach"}
