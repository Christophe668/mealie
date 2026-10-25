import builtins
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from mealie.core.exceptions import NoEntryFound
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.household.household import HouseholdRecipeUpdate
from mealie.schema.household.recipe_feedback import (
    FeedbackVerdict,
    RecipeFeedbackCreate,
    RecipeFeedbackOut,
    RecipeFeedbackPagination,
    RecipeFeedbackSummary,
)
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_timeline_events import RecipeTimelineEventCreate, TimelineEventType
from mealie.schema.user.user import PrivateUser, UserRatingCreate
from mealie.services._base_service import BaseService
from mealie.services.household_services.household_service import HouseholdService

VERDICT_RATING: dict[FeedbackVerdict, int] = {
    FeedbackVerdict.loved: 5,
    FeedbackVerdict.ok: 3,
    FeedbackVerdict.never_again: 1,
}

# Timeline subjects are server-side English (spec § 2).
VERDICT_SUBJECT: dict[FeedbackVerdict, str] = {
    FeedbackVerdict.loved: "Loved it",
    FeedbackVerdict.ok: "It was fine",
    FeedbackVerdict.never_again: "Not again",
}


class FutureMadeOnError(ValueError):
    """`made_on` is later than tomorrow (server local date + 1 day of time-zone slack)."""


def local_noon(day: date) -> datetime:
    """`day` at 12:00 in the server's local time zone, tz-aware (the offset that applies on that day)."""
    return datetime.combine(day, time(12)).astimezone()


def move_last_made_forward(repos: AllRepositories, user: PrivateUser, recipe: Recipe, made_at: datetime) -> None:
    """Set the user's household's last made for `recipe` to `made_at` only when that is later; an older cooking
    never moves it back. Shared by the feedback and cooked-meal services."""
    current = repos.household_recipes.get_by_recipe(recipe.id)
    if current is not None and current.last_made is not None:
        last_made = current.last_made
        if last_made.tzinfo is None:  # stored as naive UTC; only an unrefreshed in-session value can be naive
            last_made = last_made.replace(tzinfo=UTC)
        if last_made >= made_at:
            return
    household_service = HouseholdService(user.group_id, user.household_id, repos)
    household_service.set_household_recipe(recipe.slug, HouseholdRecipeUpdate(last_made=made_at))


class RecipeFeedbackService(BaseService):
    """Recording and removing recipe feedback, with its side effects on last made, rating and timeline (spec § 2)."""

    def __init__(self, repos: AllRepositories, user: PrivateUser):
        self.repos = repos
        self.user = user
        self.feedback = repos.recipe_feedback
        super().__init__()

    # ------------------------------------------------------------------ reads

    def list(self, recipe_id: UUID | None, page: int = 1, per_page: int = 50) -> RecipeFeedbackPagination:
        """The household's feedback, newest `made_on` first, optionally for one recipe."""
        return self.feedback.page_newest_first(page, per_page, recipe_id)

    def summaries(self, recipe_ids: builtins.list[UUID]) -> dict[UUID, RecipeFeedbackSummary]:
        """Per-recipe summaries for the household; recipes without feedback (or deleted ones) are omitted."""
        return self.feedback.summaries(recipe_ids)

    def _get_recipe_or_raise(self, recipe_id: UUID) -> Recipe:
        # Recipes are shared across the households of a group, but `repos.recipes` is household-scoped: look the
        # recipe up group-wide (as `HouseholdService._get_recipe` does). A recipe in another group is not found.
        group_recipes = get_repositories(self.repos.session, group_id=self.user.group_id, household_id=None).recipes
        recipe = group_recipes.get_one(recipe_id, "id")
        if recipe is None:
            raise NoEntryFound("Recipe not found.")
        return recipe

    def _get_or_raise(self, feedback_id: UUID) -> RecipeFeedbackOut:
        # household-scoped: another household's feedback is not found
        row = self.feedback.get_one(feedback_id)
        if row is None:
            raise NoEntryFound("Recipe feedback not found.")
        return row

    # ------------------------------------------------------------------ writes

    def record(self, data: RecipeFeedbackCreate, today: date | None = None) -> RecipeFeedbackOut:
        """Record how a recipe went: the row, its timeline event, the user's rating and the household's last made.

        Everything is validated before the first write; raises `FutureMadeOnError` (a `ValueError`) when
        `made_on` is later than tomorrow (one day of slack for a cook ahead of the server's time zone), and
        `NoEntryFound` when the recipe is not in the user's group. Either way nothing is written.

        Each repository call commits on its own. Order: timeline event, feedback row (carrying the event id),
        rating, last made. A failure midway can leave a timeline comment without its row, or a row whose rating
        or last made was not applied, but never a rating or last made without the feedback that caused it.
        """
        today = today or datetime.now().astimezone().date()
        latest = today + timedelta(days=1)
        if data.made_on is not None and data.made_on > latest:
            raise FutureMadeOnError(
                f"made_on cannot be later than {latest.isoformat()}, got {data.made_on.isoformat()}."
            )
        recipe = self._get_recipe_or_raise(data.recipe_id)
        made_on = data.made_on or today
        made_at = local_noon(made_on)

        event = self.repos.recipe_timeline_events.create(
            RecipeTimelineEventCreate(
                recipe_id=recipe.id,
                user_id=self.user.id,
                subject=VERDICT_SUBJECT[data.verdict],
                event_type=TimelineEventType.comment,
                message=data.note,
                timestamp=made_at,
            )
        )

        row = self.feedback.create(
            {
                **data.model_dump(),
                "made_on": made_on,
                "user_id": self.user.id,
                "timeline_event_id": event.id,
            }
        )

        self._set_rating(recipe, VERDICT_RATING[data.verdict])
        move_last_made_forward(self.repos, self.user, recipe, made_at)
        return row

    def delete(self, feedback_id: UUID) -> RecipeFeedbackOut:
        """Delete a feedback row and its timeline event; last made and rating are left as they are.

        Raises `NoEntryFound` for an unknown id or another household's row. Order: the timeline event first
        (when it still exists; the user may have removed it from the timeline already), then the row.
        """
        row = self._get_or_raise(feedback_id)
        if row.timeline_event_id is not None and self.repos.recipe_timeline_events.get_one(row.timeline_event_id):
            self.repos.recipe_timeline_events.delete(row.timeline_event_id)
        return self.feedback.delete(row.id)

    def _set_rating(self, recipe: Recipe, rating: int) -> None:
        """Set the recording user's rating, keeping their favourite flag (as `routes/users/ratings.py` does)."""
        existing = self.repos.user_ratings.get_by_user_and_recipe(self.user.id, recipe.id)
        if existing is None:
            self.repos.user_ratings.create(
                UserRatingCreate(user_id=self.user.id, recipe_id=recipe.id, rating=rating, is_favorite=False)
            )
        else:
            existing.rating = rating
            self.repos.user_ratings.update(existing.id, existing)
