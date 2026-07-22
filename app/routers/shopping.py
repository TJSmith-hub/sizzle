"""Shopping list routes: a persistent, editable list + print view.

Unlike recipes, the list itself has no "id" in the URL -- there is one running
list for this single-user app. Items are added either from a recipe (see
``routers.recipes``) or typed in directly here. The preferred display unit
system travels as a query param (``?system=metric``) so it stays bookmarkable,
same as the print view.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.config import DEFAULT_UNIT_SYSTEM
from app.database import get_db
from app.models import Recipe, ShoppingListItem
from app.services import units
from app.services.shopping_list import build_shopping_view
from app.templating import templates

router = APIRouter()


def _system(value: str) -> str:
    value = (value or "").lower()
    return value if value in ("metric", "imperial") else DEFAULT_UNIT_SYSTEM


def _all_items(db: Session) -> list[ShoppingListItem]:
    stmt = select(ShoppingListItem).order_by(ShoppingListItem.created_at)
    return list(db.scalars(stmt))


def _parse_quantity(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@router.get("/shopping-list", response_class=HTMLResponse)
def shopping_view(request: Request, db: Session = Depends(get_db), system: str = ""):
    system = _system(system)
    items = _all_items(db)
    aisles = build_shopping_view(items, system) if items else []
    return templates.TemplateResponse(
        request,
        "shopping_list.html",
        {"aisles": aisles, "system": system, "has_items": bool(items)},
    )


@router.get("/shopping-list/print", response_class=HTMLResponse)
def shopping_print(request: Request, db: Session = Depends(get_db), system: str = ""):
    system = _system(system)
    items = _all_items(db)
    aisles = build_shopping_view(items, system) if items else []
    sources = sorted({i.source for i in items if i.source})
    return templates.TemplateResponse(
        request,
        "shopping_print.html",
        {"aisles": aisles, "system": system, "sources": sources},
    )


@router.post("/shopping-list/add-recipes")
def add_recipes(db: Session = Depends(get_db), recipe: list[int] = Form(default=[])):
    if recipe:
        stmt = select(Recipe).where(Recipe.id.in_(recipe))
        for r in db.scalars(stmt).unique():
            crud.add_recipe_to_shopping_list(db, r)
    return RedirectResponse("/shopping-list", status_code=303)


@router.post("/shopping-list/items")
def add_item(
    db: Session = Depends(get_db),
    name: str = Form(...),
    quantity: str = Form(""),
    unit: str = Form(""),
    note: str = Form(""),
):
    name = name.strip()
    if name:
        crud.add_shopping_item(
            db,
            name=name,
            quantity=_parse_quantity(quantity),
            unit=units.normalize_unit(unit) if unit.strip() else None,
            note=note.strip() or None,
            source=None,
        )
    return RedirectResponse("/shopping-list", status_code=303)


@router.post("/shopping-list/items/{item_id}/update")
def update_item(
    item_id: int,
    db: Session = Depends(get_db),
    name: str = Form(...),
    quantity: str = Form(""),
    unit: str = Form(""),
    note: str = Form(""),
):
    item = db.get(ShoppingListItem, item_id)
    if item is not None:
        name = name.strip()
        if name:
            item.name = name
        item.quantity = _parse_quantity(quantity)
        item.quantity_max = None
        item.unit = units.normalize_unit(unit) if unit.strip() else None
        item.note = note.strip() or None
        db.commit()
    return RedirectResponse("/shopping-list", status_code=303)


@router.post("/shopping-list/items/{item_id}/toggle")
def toggle_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ShoppingListItem, item_id)
    if item is not None:
        item.checked = not item.checked
        db.commit()
    return {"ok": True, "checked": item.checked if item is not None else False}


@router.post("/shopping-list/items/{item_id}/delete")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ShoppingListItem, item_id)
    if item is not None:
        db.delete(item)
        db.commit()
    return RedirectResponse("/shopping-list", status_code=303)


@router.post("/shopping-list/clear-checked")
def clear_checked(db: Session = Depends(get_db)):
    for item in db.scalars(select(ShoppingListItem).where(ShoppingListItem.checked.is_(True))):
        db.delete(item)
    db.commit()
    return RedirectResponse("/shopping-list", status_code=303)


@router.post("/shopping-list/clear-all")
def clear_all(db: Session = Depends(get_db)):
    for item in db.scalars(select(ShoppingListItem)):
        db.delete(item)
    db.commit()
    return RedirectResponse("/shopping-list", status_code=303)
