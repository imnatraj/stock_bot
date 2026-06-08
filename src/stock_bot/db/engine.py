"""Database engine and session management for MariaDB using SQLAlchemy 2.x.

Creates an engine from environment settings and provides a session factory
and transaction helper. Uses PyMySQL driver and connection pooling tuned for
small production workloads.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    user = os.getenv("MYSQL_USER") or os.getenv("DB_USER")
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD")
    host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "localhost")
    port = os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", "3306")
    db = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME")
    if not all([user, password, host, port, db]):
        raise RuntimeError("Database environment variables not fully set")
    # Ensure UTF8MB4 and InnoDB via connect args
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4"


# Engine created once per process
def create_db_engine(echo: bool = False):
    url = get_database_url()
    logger.info("Creating DB engine for %s", url.split("@")[-1])
    engine = create_engine(
        url,
        echo=echo,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
        pool_pre_ping=True,
        future=True,
    )
    return engine


_ENGINE = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db(echo: bool = False) -> None:
    global _ENGINE, _SessionLocal
    if _ENGINE is None:
        _ENGINE = create_db_engine(echo=echo)
        _SessionLocal = sessionmaker(bind=_ENGINE, autoflush=False, expire_on_commit=False, future=True)


def get_engine():
    if _ENGINE is None:
        init_db()
    return _ENGINE


@contextmanager
def get_session() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    if _SessionLocal is None:
        init_db()
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
