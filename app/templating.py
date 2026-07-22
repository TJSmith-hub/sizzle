"""Shared Jinja2 template environment with custom filters."""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.services import units

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _minutes(value: int | None) -> str:
    """Render minutes as e.g. '1 hr 30 min'."""
    if not value:
        return ""
    hours, mins = divmod(int(value), 60)
    parts = []
    if hours:
        parts.append(f"{hours} hr")
    if mins:
        parts.append(f"{mins} min")
    return " ".join(parts) or "0 min"


def _aisle_label(value: str) -> str:
    return value.replace("_", " ").title()


# Register filters used across templates.
templates.env.filters["minutes"] = _minutes
templates.env.filters["unit_label"] = units.unit_label
templates.env.filters["format_quantity"] = units.format_quantity
templates.env.filters["aisle_label"] = _aisle_label

# Canonical unit code -> friendly label, shared so unit <select>s are rendered
# from one source of truth rather than hand-maintained option lists.
templates.env.globals["unit_options"] = units.UNIT_LABELS
