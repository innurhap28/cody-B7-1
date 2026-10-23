"""SQLite runtime and request-scoped units of work for the shortform service."""
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def create_db_engine(url: str) -> Engine:
    parsed = make_url(url)
    options = {"check_same_thread": False, "timeout": 5} if parsed.get_backend_name() == "sqlite" else {}
    connection_pool = create_engine(parsed, connect_args=options, pool_pre_ping=True, hide_parameters=True)
    if parsed.get_backend_name() == "sqlite":
        @event.listens_for(connection_pool, "connect")
        def configure_sqlite(connection, _record):
            with_cursor = connection.cursor()
            try:
                with_cursor.execute("PRAGMA foreign_keys = ON")
                with_cursor.execute("PRAGMA busy_timeout = 5000")
            finally:
                with_cursor.close()
    return connection_pool


engine = create_db_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as unit_of_work:
        yield unit_of_work
