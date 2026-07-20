"""Recipe routes: browse, add-by-URL, review, save, detail, edit, delete."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import crud
from app.config import DEFAULT_UNIT_SYSTEM
from app.database import get_db
from app.models import Recipe, Tag, recipe_tags
from app.presenters import (
    recipe_to_detail_dict,
    recipe_to_review_dict,
    scraped_to_review_dict,
)
from app.schemas import RecipeIn
from app.services.scraper import ScrapeError, scrape_recipe
from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db), q: str = "", tag: str = ""):
    stmt = select(Recipe)
    q = q.strip()
    tag = tag.strip()

    if q:
        like = f"%{q}%"
        # Match title, or any tag name.
        stmt = (
            stmt.outerjoin(recipe_tags, Recipe.id == recipe_tags.c.recipe_id)
            .outerjoin(Tag, Tag.id == recipe_tags.c.tag_id)
            .where(or_(Recipe.title.ilike(like), Tag.name.ilike(like)))
            .distinct()
        )
    if tag:
        stmt = (
            stmt.join(recipe_tags, Recipe.id == recipe_tags.c.recipe_id)
            .join(Tag, Tag.id == recipe_tags.c.tag_id)
            .where(Tag.name == tag.lower())
            .distinct()
        )

    stmt = stmt.order_by(Recipe.created_at.desc())
    recipes = list(db.scalars(stmt).unique())

    all_tags = list(db.scalars(select(Tag).order_by(Tag.name)))

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "recipes": recipes,
            "all_tags": all_tags,
            "q": q,
            "active_tag": tag,
        },
    )


@router.get("/recipes/add", response_class=HTMLResponse)
def add_form(request: Request):
    return templates.TemplateResponse(request, "add.html", {"error": None, "url": ""})


@router.post("/recipes/scrape", response_class=HTMLResponse)
def scrape(request: Request, url: str = Form(...)):
    try:
        scraped = scrape_recipe(url)
    except ScrapeError as exc:
        return templates.TemplateResponse(
            request,
            "add.html",
            {"error": str(exc), "url": url},
            status_code=422,
        )

    review = scraped_to_review_dict(scraped)
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "recipe": review,
            "recipe_json": json.dumps(review),
            "action": "/recipes",
            "heading": "Review recipe before saving",
            "submit_label": "Save recipe",
        },
    )


@router.post("/recipes")
def create(request: Request, db: Session = Depends(get_db), payload: str = Form(...)):
    data = _parse_payload(payload)
    recipe = crud.create_recipe(db, data)
    return RedirectResponse(url=f"/recipes/{recipe.id}", status_code=303)


@router.get("/recipes/{recipe_id}", response_class=HTMLResponse)
def detail(request: Request, recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    default_system = recipe.preferred_system or DEFAULT_UNIT_SYSTEM
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "recipe": recipe,
            "recipe_json": json.dumps(recipe_to_detail_dict(recipe)),
            "default_system": default_system,
        },
    )


@router.get("/recipes/{recipe_id}/edit", response_class=HTMLResponse)
def edit_form(request: Request, recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    review = recipe_to_review_dict(recipe)
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "recipe": review,
            "recipe_json": json.dumps(review),
            "action": f"/recipes/{recipe_id}/update",
            "heading": f"Edit “{recipe.title}”",
            "submit_label": "Save changes",
        },
    )


@router.post("/recipes/{recipe_id}/update")
def update(request: Request, recipe_id: int, db: Session = Depends(get_db), payload: str = Form(...)):
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    data = _parse_payload(payload)
    crud.update_recipe(db, recipe, data)
    return RedirectResponse(url=f"/recipes/{recipe_id}", status_code=303)


@router.post("/recipes/{recipe_id}/delete")
def delete(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if recipe is not None:
        db.delete(recipe)
        db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.post("/recipes/{recipe_id}/add-to-shopping-list")
def add_to_shopping_list(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    added = crud.add_recipe_to_shopping_list(db, recipe)
    return RedirectResponse(url=f"/shopping-list?added={added}", status_code=303)


def _parse_payload(payload: str) -> RecipeIn:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}") from exc
    try:
        return RecipeIn.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
