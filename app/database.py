"""SQLAlchemy engine, session factory, and declarative base."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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
    # Kept local to avoid a circular import (models imports Base from here).
    from app import models  # noqa: F401, PLC0415

    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """Add any model columns missing from an already-created database.

    ``create_all`` only creates missing *tables*, never alters existing ones, so
    when a new column is introduced this backfills it on older SQLite files with
    a lightweight ADD COLUMN. It compares every mapped table against the live
    schema rather than hard-coding one column, so future additions need no change
    here. Only *nullable* columns can be added this way (SQLite can't append a
    NOT NULL column to a populated table); every post-v1 column so far has been.
    """
    from app import models  # noqa: F401, PLC0415 - register models; avoids circular import

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all already built this table in full
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have or not column.nullable:
                continue
            ddl = column.type.compile(engine.dialect)
            with engine.begin() as conn:
                conn.execute(
                    text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl}")
                )
