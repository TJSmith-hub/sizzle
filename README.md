# 🔥 Sizzle

> **Note:** This project was built with substantial help from AI coding tools.
> The code has been reviewed and tested, but you should read it yourself before
> running it on anything you care about. Provided as-is under the MIT license,
> with no warranty (see [LICENSE](LICENSE)).

A self-hosted, single-user recipe manager built for a home server / NAS. It
imports recipes from a URL, keeps ingredients as **structured data** (grouped
into sections, parsed into quantity + unit + name), and does three things most
tools don't do well:

1. **Ingredient grouping** — reconstructs sections like *“For the dough” / “For
   the filling”* from the flat scraped list, with an easy review screen to fix
   the auto-grouping before saving.
2. **Recipe scaling & unit conversion** — change the serving count and every
   quantity recalculates live; toggle metric ⇄ imperial (volume↔volume and
   weight↔weight only — never the density-dependent volume↔weight), including
   oven temperatures in the instructions.
3. **Aisle-grouped shopping lists** — select several recipes, merge duplicate
   ingredients across them, group everything by grocery aisle, and print a clean
   checklist.

## Stack

- **Backend:** Python + FastAPI
- **Database:** SQLite via SQLAlchemy (single file, mounted as a Docker volume)
- **Frontend:** server-rendered Jinja2 templates + vanilla JS (no build step)
- **Scraping:** [`recipe-scrapers`](https://github.com/hhursev/recipe-scrapers)
  (hundreds of sites, with schema.org / JSON-LD fallback via `wild_mode`)

---

## Run it

### With Docker (recommended)

```bash
docker compose up -d
```

Then open <http://localhost:6769>.

- **Where the data lives:** the SQLite database is stored at `./data/recipes.db`
  on the host (mounted into the container at `/data/recipes.db`). It persists
  across container restarts and image upgrades. Back up the app by copying that
  one file.
- **Change the default unit system:** edit `DEFAULT_UNIT_SYSTEM` in
  `docker-compose.yml` (`metric` or `imperial`), then `docker compose up -d`.
  Users can still toggle units per-recipe in the UI.

### Updating

Pull the latest code and rebuild:

```bash
git pull
docker compose up -d --build
```

`--build` rebuilds the image with the new code; `-d` recreates the container.
Your recipes live in `./data/recipes.db` on the host and are preserved across
the rebuild. The schema is migrated automatically on startup — new columns are
added in place, so an existing database keeps working.

---

## Dev

Everything below is for running from source or hacking on the app.

### Run locally (without Docker)

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv run uvicorn app.main:app --reload
```

`uv run` creates the virtual environment from `pyproject.toml` / `uv.lock` on
first use (and keeps it in sync automatically). The database defaults to
`./data/recipes.db`. To update, `git pull` and run again — `uv run` re-syncs the
environment from `uv.lock` if any dependencies changed.

### Run the tests

```bash
uv run pytest
```

The suite covers the tricky pure-logic pieces: ingredient parsing, the grouping
heuristic, unit conversion, cooking-fraction rounding, and aisle categorization.

### Lint

```bash
uv run ruff check      # lint (see [tool.ruff] in pyproject.toml)
uv run ruff format     # optional: auto-format
```

### Customizing

#### Grocery aisle categories — `app/services/aisles.py`

This is the file to edit for your own store layout. It contains:

- `AISLE_ORDER` — the aisles in the order they print on the shopping list.
- `AISLE_KEYWORDS` — a `{aisle: [keywords]}` dictionary. Each ingredient is filed
  under the **first** aisle (in `AISLE_ORDER`) whose keyword matches its name.
  Matching is case-insensitive and word-boundary based (so `corn` won't match
  `cornflour`).

Add/remove keywords freely; to make one aisle win ties, move it earlier in
`AISLE_ORDER`. Anything unmatched falls into `other`.

#### Grouping heuristic thresholds — `app/services/grouping.py`

Constants at the top control how section headers are detected:

- `HEADER_MAX_LEN` — max length for the “short line” rules.
- `HEADER_PREFIXES` — phrases that mark a header (`for the`, `to serve`, …).
- `ENABLE_SHORT_PHRASE_RULE` — off by default. If `True`, any short line with no
  units/digits is treated as a header. This is more aggressive and will
  occasionally misclassify bare ingredients (e.g. `salt`), which is why it's off;
  the default rules (colon-terminated, known prefixes, ALL-CAPS) are conservative.

The review screen always lets you fix grouping by hand, so a missed header is
cheap — it's just one “move to group” click.

#### Ingredient parser & units — `app/services/parser.py`, `app/services/units.py`

`parser.py` turns a raw line into `{quantity, quantity_max, unit, name}` (handling
fractions, unicode fractions, mixed numbers, and ranges). `units.py` holds the
unit synonym map and the fixed conversion factors — add a unit synonym there if
the parser is missing one you use often.

### Data model

- **Recipe** — title, source URL, image, servings, prep/cook/total time (minutes),
  instructions (ordered JSON list), tags (many-to-many).
- **IngredientGroup** — belongs to a recipe; `title` is null for the default
  (ungrouped) section; ordered by `position`.
- **Ingredient** — belongs to a group; keeps `raw_text` (always authoritative)
  plus parsed `quantity` / `quantity_max` / `unit` / `name`, and a `parsed` flag.
  Lines that couldn't be parsed keep `parsed = False` and are shown verbatim
  (never scaled or converted).

Tables are created automatically on first startup.

## Notes & non-goals

- Single-user; there is **no authentication**. Run it on your private network.
- No nutrition data, no mobile app, and **no volume↔weight conversion** (that's
  ingredient-density dependent and unreliable with fixed factors).

## License

[MIT](LICENSE) — do what you like with it.
