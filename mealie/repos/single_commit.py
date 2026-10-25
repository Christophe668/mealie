from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

_ACTIVE_KEY = "single_commit_active"


@contextmanager
def single_commit(session: Session) -> Iterator[None]:
    """Run several repository writes as one transaction.

    Mealie's repositories commit on every write. Inside this block `session.commit` behaves as `session.flush`, so
    the writes reach the database (ids, constraints) but stay uncommitted; on normal exit the session commits once,
    on an exception it rolls back and re-raises. `commit` is always restored. A nested block is a no-op: the
    outermost one decides.
    """
    if session.info.get(_ACTIVE_KEY):
        yield
        return

    # shadow the class method with an instance attribute; remember any instance attribute already there
    previous = session.__dict__.get("commit")
    session.info[_ACTIVE_KEY] = True
    setattr(session, "commit", session.flush)  # noqa: B010 - mypy refuses assigning to a method

    def restore() -> None:
        if previous is None:
            del session.__dict__["commit"]
        else:
            setattr(session, "commit", previous)  # noqa: B010
        session.info.pop(_ACTIVE_KEY, None)

    try:
        yield
    except BaseException:
        restore()
        session.rollback()
        raise
    restore()
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
