from __future__ import annotations

import atexit

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def build_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")
    kwargs = {
        "future": True,
        "pool_pre_ping": True,
        "pool_recycle": settings.db_pool_recycle_s,
    }
    if is_sqlite:
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
        kwargs["connect_args"] = {"connect_timeout": settings.db_connect_timeout_s}
    return create_engine(settings.database_url, **kwargs)


def build_session_factory(engine: Engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


engine = build_engine()
SessionLocal = build_session_factory(engine)
atexit.register(engine.dispose)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
