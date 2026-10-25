"""Importing a recipe from a web page, shared by `POST /api/recipes/create/url` (and its stream and
HTML variants) and the MCP `import_recipe_from_url` tool (spec § 3.2).

`import_from_web` scrapes the page with Mealie's scraper (`create_from_html`, which fetches through
`safehttp` and its SSRF, size and time safeguards), applies the scraped tags and categories, and
saves through `RecipeService.create_one`. It never publishes: each caller publishes `recipe_created`
its own way.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from mealie.db.models.recipe.recipe import RecipeModel
from mealie.lang.providers import Translator
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.recipe.recipe import Recipe
from mealie.services.recipe.recipe_service import RecipeService
from mealie.services.scraper.scraped_extras import ScrapedExtras, ScraperContext
from mealie.services.scraper.scraper import create_from_html

Scrape = Callable[..., Awaitable[tuple[Recipe, ScrapedExtras | None]]]
Prepare = Callable[[Recipe, ScrapedExtras | None], Awaitable[None]]


async def import_from_web(
    repos: AllRepositories,
    service: RecipeService,
    translator: Translator,
    url: str,
    html: str | None,
    include_tags: bool,
    include_categories: bool,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
    *,
    prepare: Prepare | None = None,
    scrape: Scrape = create_from_html,
) -> Recipe:
    """Scrapes `url` (or the given `html`), applies the scraped organizers and saves the recipe.

    Scraper failures propagate unchanged (the REST route turns them into its SSE error, the MCP
    tool into a readable error); nothing is saved then.

    - `prepare`, when given, runs on the scraped recipe before the save *instead of* the default
      organizer handling (which creates every scraped tag and category with `ScrapedExtras`). The
      MCP tool uses it to parse the ingredients and to resolve the organizers itself, so it can
      undo every row it created if the save fails.
    - `scrape` is the scraper entry point. The REST controller passes the `create_from_html` it
      imports, so the existing route tests that patch it there keep working.
    """
    recipe, extras = await scrape(
        url,
        repos,
        translator,
        html,
        on_progress=on_progress,
        include_tags=include_tags,
        include_categories=include_categories,
    )

    if prepare is not None:
        await prepare(recipe, extras)
    elif extras is not None:
        if include_tags:
            recipe.tags = extras.use_tags(ScraperContext(repos))
        if include_categories:
            recipe.recipe_category = extras.use_categories(ScraperContext(repos))

    return service.create_one(recipe)


def normalise_source_url(url: str) -> str:
    """The form two source URLs are compared in: scheme and host lower-cased, the fragment and a
    trailing "/" dropped, the query string kept (a different query is a different page).

    "HTTPS://Example.com/r/#step-2" and "https://example.com/r" are the same; "…/r?page=2" isn't."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def find_imported_recipe(session: Session, group_id: UUID, url: str) -> UUID | None:
    """The id of the earliest recipe in the group (any household) whose source URL is `url`,
    compared with `normalise_source_url`.

    Stored `org_url` values are normalised here, in Python, so older rows match without being
    rewritten; only the `id` and `org_url` columns are read. A stored value that isn't a valid URL
    (Mealie lets a user type any source) is skipped, so one bad row can't block every import."""
    target = normalise_source_url(url)
    stmt = (
        sa.select(RecipeModel.id, RecipeModel.org_url)
        .where(RecipeModel.group_id == group_id, RecipeModel.org_url.is_not(None))
        .order_by(RecipeModel.created_at)
    )
    for row in session.execute(stmt):
        if not row.org_url:
            continue
        try:
            stored = normalise_source_url(row.org_url)
        except ValueError:  # e.g. "http://[::1": urlsplit refuses it
            continue
        if stored == target:
            return row.id
    return None
