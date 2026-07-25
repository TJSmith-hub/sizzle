"""Tests for the lightweight schema reconciliation run at startup.

``_sync_columns`` brings an already-created database into line with the current
models -- adding newly-introduced nullable columns and dropping columns a model
no longer defines. The latter guards against the failure that a lingering
``NOT NULL`` column with no default (left behind when a column is removed from a
model) breaks every insert on older databases.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, _sync_columns
from app.models import ShoppingListItem


def _legacy_engine(db_path):
    """An engine whose shopping_list_items table still has the removed, legacy
    ``position INTEGER NOT NULL`` column (no default) -- mimicking a DB created
    before that column was dropped from the model."""
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE shopping_list_items"))
        conn.execute(
            text(
                "CREATE TABLE shopping_list_items ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "name VARCHAR(300) NOT NULL, "
                "quantity FLOAT, "
                "quantity_max FLOAT, "
                "unit VARCHAR(16), "
                "note VARCHAR(300), "
                "source VARCHAR(300), "
                "checked BOOLEAN NOT NULL, "
                "position INTEGER NOT NULL, "  # removed from the model; no default
                "created_at DATETIME NOT NULL)"
            )
        )
    return engine


def test_sync_columns_drops_column_removed_from_model(tmp_path):
    engine = _legacy_engine(tmp_path / "legacy.db")
    assert "position" in {c["name"] for c in inspect(engine).get_columns("shopping_list_items")}

    _sync_columns(engine)

    cols = {c["name"] for c in inspect(engine).get_columns("shopping_list_items")}
    assert "position" not in cols


def test_insert_succeeds_after_reconciling_legacy_schema(tmp_path):
    """The end-to-end symptom: an ORM insert 500s against the legacy schema
    (NOT NULL position, no default) and works once reconciled."""
    engine = _legacy_engine(tmp_path / "legacy.db")
    _sync_columns(engine)

    db = sessionmaker(bind=engine)()
    db.add(ShoppingListItem(name="pasta", quantity=400, unit="g", checked=False))
    db.commit()
    assert db.query(ShoppingListItem).count() == 1


def test_sync_columns_adds_missing_nullable_column(tmp_path):
    """The additive half of reconciliation still works: a nullable model column
    absent from an older table is backfilled with ADD COLUMN."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE shopping_list_items DROP COLUMN quantity_max"))
    assert "quantity_max" not in {
        c["name"] for c in inspect(engine).get_columns("shopping_list_items")
    }

    _sync_columns(engine)

    assert "quantity_max" in {
        c["name"] for c in inspect(engine).get_columns("shopping_list_items")
    }
