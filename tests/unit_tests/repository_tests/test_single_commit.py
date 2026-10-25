import pytest

from mealie.repos.single_commit import single_commit
from mealie.schema.household.pantry import PantryItemCreate, PantryItemOut
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


class Boom(Exception):
    pass


def _create_two(user: TestUser, created: list[PantryItemOut], fail: bool) -> None:
    for _ in range(2):
        created.append(user.repos.pantry_items.create(PantryItemCreate(name=random_string(10))))
    if fail:
        raise Boom()


def _exists(user: TestUser, item: PantryItemOut) -> bool:
    user.repos.session.expire_all()
    return user.repos.pantry_items.get_one(item.id) is not None


def test_single_commit_commits_once_and_rolls_back(unique_user: TestUser):
    session = unique_user.repos.session

    failed: list[PantryItemOut] = []
    with pytest.raises(Boom):
        with single_commit(session):
            _create_two(unique_user, failed, fail=True)
    assert len(failed) == 2
    assert not any(_exists(unique_user, row) for row in failed)
    assert "commit" not in session.__dict__  # the real commit is back

    kept: list[PantryItemOut] = []
    with single_commit(session):
        _create_two(unique_user, kept, fail=False)
    session.rollback()  # nothing pending: the block committed
    assert all(_exists(unique_user, row) for row in kept)
    assert "commit" not in session.__dict__


def test_single_commit_nested_is_a_no_op(unique_user: TestUser):
    session = unique_user.repos.session

    with pytest.raises(Boom):
        with single_commit(session):
            with single_commit(session):
                inner = unique_user.repos.pantry_items.create(PantryItemCreate(name=random_string(10)))
            # the inner block's exit did not commit
            raise Boom()
    assert not _exists(unique_user, inner)
    assert "commit" not in session.__dict__
