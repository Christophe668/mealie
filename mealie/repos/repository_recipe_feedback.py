from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select, func, select

from mealie.db.models.household.recipe_feedback import RecipeFeedback
from mealie.schema.household.recipe_feedback import FeedbackVerdict, RecipeFeedbackOut, RecipeFeedbackSummary

from .repository_generic import HouseholdRepositoryGeneric

# Newest `made_on` first, then newest recorded; `id` makes ties (one flush, a coarse clock) deterministic.
_NEWEST_FIRST = (RecipeFeedback.made_on.desc(), RecipeFeedback.created_at.desc(), RecipeFeedback.id.desc())


class RepositoryRecipeFeedback(HouseholdRepositoryGeneric[RecipeFeedbackOut, RecipeFeedback]):
    def _with_scope(self, data: RecipeFeedbackOut | BaseModel | dict) -> dict:
        """Return `data` as a dict carrying this repository's scope.

        A scoped repository always writes its own `group_id`/`household_id`, whatever the caller passed;
        only an unscoped repository honours the ids in `data`.
        """
        values = dict(data) if isinstance(data, dict) else data.model_dump()
        if self.group_id is not None:
            values["group_id"] = self.group_id
        if self.household_id is not None:
            values["household_id"] = self.household_id
        return values

    def create(self, data: RecipeFeedbackOut | BaseModel | dict) -> RecipeFeedbackOut:
        return super().create(self._with_scope(data))

    def create_many(self, data: Iterable[RecipeFeedbackOut | BaseModel | dict]) -> list[RecipeFeedbackOut]:
        return super().create_many([self._with_scope(item) for item in data])

    def _scope(self, stmt: Select) -> Select:
        if self.group_id:
            stmt = stmt.filter(RecipeFeedback.group_id == self.group_id)
        if self.household_id:
            stmt = stmt.filter(RecipeFeedback.household_id == self.household_id)
        return stmt

    def _newest_first(self, limit: int | None, recipe_id: UUID | None = None) -> list[RecipeFeedbackOut]:
        stmt = self._scope(select(RecipeFeedback).options(*self.schema.loader_options()))
        if recipe_id is not None:
            stmt = stmt.filter(RecipeFeedback.recipe_id == recipe_id)
        stmt = stmt.order_by(*_NEWEST_FIRST)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = self.session.execute(stmt).unique().scalars().all()
        return [self.schema.model_validate(row) for row in rows]

    def for_recipe(self, recipe_id: UUID, limit: int | None = None) -> list[RecipeFeedbackOut]:
        """One recipe's feedback, newest `made_on` first, then newest recorded."""
        return self._newest_first(limit, recipe_id)

    def latest(self, limit: int) -> list[RecipeFeedbackOut]:
        """The household's latest feedback across recipes, in the same order as `for_recipe`."""
        return self._newest_first(limit)

    def summaries(self, recipe_ids: list[UUID]) -> dict[UUID, RecipeFeedbackSummary]:
        """Per-recipe summary for the given recipes, in two queries; recipes without feedback are omitted."""
        if not recipe_ids:
            return {}

        counts_stmt = self._scope(
            select(RecipeFeedback.recipe_id, RecipeFeedback.verdict, func.count())
            .filter(RecipeFeedback.recipe_id.in_(recipe_ids))
            .group_by(RecipeFeedback.recipe_id, RecipeFeedback.verdict)
        )
        counts: dict[UUID, dict[str, int]] = {}
        for recipe_id, verdict, count in self.session.execute(counts_stmt).all():
            counts.setdefault(recipe_id, {})[verdict] = count

        rank = (
            func.row_number()
            .over(
                partition_by=RecipeFeedback.recipe_id,
                order_by=_NEWEST_FIRST,
            )
            .label("rank")
        )
        ranked = self._scope(
            select(RecipeFeedback.recipe_id, RecipeFeedback.verdict, RecipeFeedback.made_on, rank).filter(
                RecipeFeedback.recipe_id.in_(recipe_ids)
            )
        ).subquery()
        latest_stmt = select(ranked.c.recipe_id, ranked.c.verdict, ranked.c.made_on).filter(ranked.c.rank == 1)

        summaries: dict[UUID, RecipeFeedbackSummary] = {}
        for recipe_id, verdict, made_on in self.session.execute(latest_stmt).all():
            per_verdict = counts.get(recipe_id, {})
            summaries[recipe_id] = RecipeFeedbackSummary(
                last_verdict=FeedbackVerdict(verdict),
                last_made_on=made_on,
                loved=per_verdict.get(FeedbackVerdict.loved.value, 0),
                ok=per_verdict.get(FeedbackVerdict.ok.value, 0),
                never_again=per_verdict.get(FeedbackVerdict.never_again.value, 0),
                total=sum(per_verdict.values()),
            )
        return summaries
