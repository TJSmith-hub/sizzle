"""SQLAlchemy engine, session factory, and declarative base."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_PATH

# Ensure the directory holding the SQLite file exists (e.g. the mounted volume).
Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# check_same_thread=False is required because FastAPI may access the session
# from different threads within a request lifecycle.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db():
    """FastAPI dependency that yields a database session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called on application startup."""
    # Import models so they are registered on the metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
