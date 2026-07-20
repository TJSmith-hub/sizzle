"""Shopping list routes: aisle-grouped view and print view.

Selection and unit system travel as query params (``?recipe=1&recipe=2&system=metric``)
so the in-app view and the print view share identical, bookmarkable state.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEFAULT_UNIT_SYSTEM
from app.database import get_db
from app.models import Recipe
from app.services.shopping_list import build_shopping_list
from app.templating import templates

router = APIRouter()


def _load(db: Session, recipe_ids: list[int]) -> list[Recipe]:
    if not recipe_ids:
        return []
    stmt = select(Recipe).where(Recipe.id.in_(recipe_ids))
    by_id = {r.id: r for r in db.scalars(stmt).unique()}
    # Preserve the order the user selected them in.
    return [by_id[i] for i in recipe_ids if i in by_id]


def _system(value: str) -> str:
    value = (value or "").lower()
    return value if value in ("metric", "imperial") else DEFAULT_UNIT_SYSTEM


@router.get("/shopping-list", response_class=HTMLResponse)
def shopping_view(
    request: Request,
    db: Session = Depends(get_db),
    recipe: list[int] = Query(default=[]),
    system: str = "",
):
    system = _system(system)
    recipes = _load(db, recipe)
    aisles = build_shopping_list(recipes, system) if recipes else []
    return templates.TemplateResponse(
        request,
        "shopping_list.html",
        {
            "recipes": recipes,
            "recipe_ids": recipe,
            "aisles": aisles,
            "system": system,
        },
    )


@router.get("/shopping-list/print", response_class=HTMLResponse)
def shopping_print(
    request: Request,
    db: Session = Depends(get_db),
    recipe: list[int] = Query(default=[]),
    system: str = "",
):
    system = _system(system)
    recipes = _load(db, recipe)
    aisles = build_shopping_list(recipes, system) if recipes else []
    return templates.TemplateResponse(
        request,
        "shopping_print.html",
        {
            "recipes": recipes,
            "aisles": aisles,
            "system": system,
        },
    )
