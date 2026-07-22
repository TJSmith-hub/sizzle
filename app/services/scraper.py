"""Fetch a recipe URL and normalize it using the recipe-scrapers library.

recipe-scrapers supports hundreds of named sites and, via ``wild_mode=True``,
falls back to generic schema.org / JSON-LD ``Recipe`` parsing for the rest.

We fetch the HTML ourselves with a browser-like User-Agent (many sites 403 the
default client UA) and then hand the HTML to ``scrape_html`` so scraping never
depends on the library's own networking.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from recipe_scrapers import scrape_html

from app.config import FETCH_TIMEOUT, FETCH_USER_AGENT
from app.services.grouping import group_ingredients
from app.services.parser import parse_ingredient

# The fetcher pulls a user-supplied URL, so it must not be steerable into the
# host's own loopback interface, the LAN, or a cloud metadata endpoint (SSRF).
# We resolve the host up front and reject non-public addresses, and — since a
# public URL can redirect into those ranges — re-validate every redirect hop.
MAX_REDIRECTS = 5
# An HTML recipe page is comfortably under a few MB; cap the (decompressed) body
# so a huge or gzip-bomb response can't exhaust memory.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_PRIVATE_URL_ERROR = (
    "That URL resolves to a private or local network address, which isn't allowed."
)


class ScrapeError(Exception):
    """Raised when a URL cannot be fetched or no usable recipe data is found."""


def _is_blocked_ip(ip: str) -> bool:
    """Whether an IP address must not be fetched (non-public or unparseable)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # can't classify it -> refuse
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _validate_public_url(url: str) -> None:
    """Reject non-http(s) URLs and any host that resolves to a non-public IP.

    Resolving here (rather than trusting the literal host) also covers hostnames
    that point at internal addresses. Raises ScrapeError on any violation.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ScrapeError("Only http:// and https:// URLs can be fetched.")
    host = parsed.hostname
    if not host:
        raise ScrapeError("That URL has no host to fetch.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ScrapeError(f"Couldn't resolve the host '{host}'.") from exc
    for info in infos:
        if _is_blocked_ip(info[4][0]):
            raise ScrapeError(_PRIVATE_URL_ERROR)


def _fetch_html(url: str) -> str:
    headers = {
        "User-Agent": FETCH_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        # Follow redirects manually so each hop's host is re-validated before it
        # is fetched (an allowlist on the first URL alone is bypassable).
        with httpx.Client(
            headers=headers, timeout=FETCH_TIMEOUT, follow_redirects=False
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                _validate_public_url(url)
                with client.stream("GET", url) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise ScrapeError("The page redirected without a destination.")
                        url = str(resp.url.join(location))
                        continue
                    resp.raise_for_status()
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            raise ScrapeError(
                                "That page is too large to fetch "
                                f"(over {MAX_RESPONSE_BYTES // (1024 * 1024)} MB)."
                            )
                        chunks.append(chunk)
                    return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
            raise ScrapeError("Too many redirects while fetching the page.")
    except httpx.HTTPStatusError as exc:
        raise ScrapeError(
            f"The page returned HTTP {exc.response.status_code}. "
            "The site may be blocking automated access."
        ) from exc
    except httpx.HTTPError as exc:
        raise ScrapeError(f"Could not fetch the page: {exc}") from exc


def _safe(fn, default=None):
    """Call a scraper method, swallowing the exceptions it raises for missing fields."""
    try:
        value = fn()
    except Exception:  # noqa: BLE001 - scraper plugins raise assorted errors for missing fields
        return default
    return value if value is not None else default


_SERVINGS_RE = re.compile(r"\d+")


def _parse_servings(yields: str | None) -> int | None:
    """Extract an integer serving count from a yields string like '4 servings'."""
    if not yields:
        return None
    if isinstance(yields, int):
        return yields
    m = _SERVINGS_RE.search(str(yields))
    return int(m.group()) if m else None


def _positive_int(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _norm(text: str) -> str:
    """Normalize a line for comparison (collapse whitespace, lowercase)."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


# A step line that instead reads like a section subtitle ("For the sauce").
_HEADING_RE = re.compile(r"^for the .{1,40}$", re.IGNORECASE)
# Names that are step numbers rather than section titles ("Step 1", "3.").
_STEP_LABEL_RE = re.compile(r"^(step\s*)?\d+\.?$", re.IGNORECASE)


def _collapse(text) -> str:
    """Collapse runs of whitespace and strip (schema text is often double-spaced)."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _is_section_name(name: str, text: str) -> bool:
    """Whether a step's ``name`` is a real section label rather than its text.

    Named-step recipes (common in WordPress Recipe Maker) give each step a short
    title like "Marinade" or "Skewer" alongside the full instruction text. Those
    make good headings. We reject names that merely repeat/truncate the text, are
    too long to be a label, are a full sentence, or are just a step number.
    """
    if not name or name == text:
        return False
    if len(name) > 40 or len(name.split()) > 6:
        return False
    return not (name.endswith((".", "!", "?")) or _STEP_LABEL_RE.match(name))


def _schema_instructions(scraper) -> list[dict] | None:
    """Build typed instructions from the page's schema.org ``recipeInstructions``.

    This is the reliable source of section structure: ``HowToSection`` entries
    carry a section ``name`` wrapping child steps, and many sites tag each
    ``HowToStep`` with a short ``name`` (e.g. "Marinade", "Bake"). Both become
    headings here -- structure the flat ``instructions_list`` throws away.

    Returns typed items only when at least one heading was found; otherwise None,
    so callers fall back to the plain-text path (no headings invented).
    """
    try:
        data = scraper.schema.data
    except Exception:  # noqa: BLE001 - no/!broken schema; caller falls back
        return None
    raw = data.get("recipeInstructions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return None

    out: list[dict] = []
    saw_heading = False

    def add_step(text) -> None:
        t = _collapse(text)
        if t:
            out.append({"type": "step", "text": t})

    for entry in raw:
        if isinstance(entry, str):
            add_step(entry)
            continue
        if not isinstance(entry, dict):
            continue
        children = entry.get("itemListElement")
        if entry.get("@type") == "HowToSection" or children:
            name = _collapse(entry.get("name"))
            if name and len(name) <= 60 and not _STEP_LABEL_RE.match(name):
                out.append({"type": "heading", "text": name})
                saw_heading = True
            for child in children or []:
                if isinstance(child, dict):
                    add_step(child.get("text") or child.get("name"))
                elif isinstance(child, str):
                    add_step(child)
        else:  # HowToStep
            name = _collapse(entry.get("name"))
            text = _collapse(entry.get("text"))
            if _is_section_name(name, text):
                out.append({"type": "heading", "text": name})
                saw_heading = True
            add_step(text or name)

    return out if (out and saw_heading) else None


def _classify_instructions(lines: list[str]) -> list[dict]:
    """Turn scraped instruction lines into typed step/heading items.

    Most lines are steps. A few sites emit section subtitles inline as their own
    line; we flag the obvious ones as headings so they don't get a step number.
    The detection is deliberately conservative (short lines that read like a
    subtitle, not a sentence) -- anything it misses is a one-click fix in the
    review editor.
    """
    out: list[dict] = []
    for line in lines:
        s = (line or "").strip()
        if not s:
            continue
        ends_sentence = s.endswith((".", "!", "?"))
        is_heading = (
            (s.endswith(":") and len(s.split()) <= 6)
            or (bool(_HEADING_RE.match(s)) and not ends_sentence)
        )
        if is_heading:
            out.append({"type": "heading", "text": s.rstrip(":").strip()})
        else:
            out.append({"type": "step", "text": s})
    return out


def _has_sections(groups: list | None) -> bool:
    """Return True if at least one group carries a real section title."""
    return bool(groups) and any(g["title"] for g in groups)


def _native_groups(scraper) -> list | None:
    """Use recipe-scrapers' own ``ingredient_groups()`` when the site supports it.

    Returns a list of ``{"title": str|None, "lines": [str, ...]}`` or None when
    the method is unavailable or raises (some site plugins error on pages whose
    markup no longer matches their hardcoded selectors).
    """
    try:
        groups = scraper.ingredient_groups()
    except Exception:  # noqa: BLE001 - plugins raise assorted errors
        return None
    out = []
    for g in groups or []:
        lines = [str(x) for x in getattr(g, "ingredients", []) if str(x).strip()]
        if not lines:
            continue
        purpose = getattr(g, "purpose", None)
        out.append({"title": (purpose or None), "lines": lines})
    return out or None


def _soup_groups(scraper, flat: list[str]) -> list | None:
    """Reconstruct sections from the page HTML via each list's sibling heading.

    Matches ingredient lists to their nearest sibling heading. Works even when
    the library's per-site grouping fails: we locate the
    ``<ul>``/``<ol>`` lists whose items match the flat ingredient list, then take
    each list's preceding-sibling heading (scoped to the same container, so we
    never grab an unrelated page heading like "Nutrition"). Falls back to None if
    it can't account for most of the ingredients.
    """
    soup = getattr(scraper, "soup", None)
    if soup is None or not flat:
        return None

    flat_set = {_norm(x) for x in flat}
    out = []
    for lst in soup.find_all(["ul", "ol"]):
        items = lst.find_all("li", recursive=False) or lst.find_all("li")
        texts = [li.get_text(" ", strip=True) for li in items]
        matched = [t for t in texts if _norm(t) in flat_set]
        # Skip lists that aren't (mostly) ingredients — e.g. nav or nutrition.
        if not matched or len(matched) < max(1, len(texts) // 2):
            continue
        heading = lst.find_previous_sibling(["h2", "h3", "h4", "h5", "h6"])
        title = heading.get_text(" ", strip=True) if heading else None
        # A heading that is itself an ingredient, or absurdly long, isn't a section.
        if title and (len(title) > 60 or _norm(title) in flat_set):
            title = None
        out.append({"title": title, "lines": matched})

    covered = sum(len(g["lines"]) for g in out)
    if covered < len(flat) * 0.6:  # didn't reliably map the list — bail out
        return None
    return out or None


def _build_groups(scraper, flat: list[str]) -> list[dict]:
    """Return grouped, parsed ingredients, preferring real site sections.

    Strategy (most reliable first): the library's native ``ingredient_groups()``,
    then an HTML/soup reconstruction, then our text-only heuristic on the flat
    list. The first strategy that actually finds titled sections wins.
    """
    raw = _native_groups(scraper)
    if not _has_sections(raw):
        soup_based = _soup_groups(scraper, flat)
        if _has_sections(soup_based):
            raw = soup_based
    if not _has_sections(raw):
        raw = [
            {"title": g["title"], "lines": g["ingredients"]}
            for g in group_ingredients(flat)
        ]

    return [
        {
            "title": g["title"],
            "ingredients": [parse_ingredient(line) for line in g["lines"]],
        }
        for g in raw
    ]


def scrape_recipe(url: str) -> dict:
    """Scrape ``url`` and return a normalized, structured recipe dict.

    Shape::

        {
          "title", "source_url", "image_url", "servings",
          "prep_time", "cook_time", "total_time",
          "instructions": [ {"type": "step"|"heading", "text": str}, ... ],
          "groups": [ {"title": str|None, "ingredients": [parsed_dict, ...]} ],
        }

    Raises ScrapeError if the page can't be fetched or has no title/ingredients.
    """
    url = url.strip()
    if not url:
        raise ScrapeError("Please enter a URL.")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    html = _fetch_html(url)

    try:
        scraper = scrape_html(html, org_url=url, wild_mode=True)
    except Exception as exc:
        raise ScrapeError(
            "Couldn't find recipe data on that page. It may not be a recipe "
            "page, or the site's format isn't supported."
        ) from exc

    title = _safe(scraper.title)
    ingredients = _safe(scraper.ingredients, default=[]) or []

    if not title and not ingredients:
        raise ScrapeError(
            "Couldn't find a recipe on that page (no title or ingredients). "
            "You can still add it manually."
        )

    # Prefer the schema's own section/step structure; fall back to the flat list
    # (with a light heading heuristic) when the page has no usable schema.
    instructions = _schema_instructions(scraper)
    if not instructions:
        lines = _safe(scraper.instructions_list, default=None)
        if not lines:
            text = _safe(scraper.instructions, default="") or ""
            lines = [s.strip() for s in text.split("\n") if s.strip()]
        instructions = _classify_instructions(lines)

    # Reconstruct ingredient sections (preferring the site's own grouping), then
    # parse each line into structured fields.
    groups = _build_groups(scraper, [str(i) for i in ingredients])

    return {
        "title": title or "Untitled recipe",
        "source_url": url,
        "image_url": _safe(scraper.image),
        "servings": _parse_servings(_safe(scraper.yields)),
        "prep_time": _positive_int(_safe(scraper.prep_time)),
        "cook_time": _positive_int(_safe(scraper.cook_time)),
        "total_time": _positive_int(_safe(scraper.total_time)),
        "instructions": instructions,
        "groups": groups,
    }
