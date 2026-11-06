"""Which workspace (client company) the current request or background job belongs to.

Every request sets it from the signed-in user's session; background jobs set it from the account
they work on. All workspace-owned data (accounts, research, seller profile, decks, pitches, feedback
learning) is read and written for the current workspace only.
"""
import contextvars
from contextlib import contextmanager

from . import config, db

_current: contextvars.ContextVar[int | None] = contextvars.ContextVar("workspace_id", default=None)


def current() -> int:
    wid = _current.get()
    if wid is None:
        if not config.REQUIRE_LOGIN:
            return 1  # single-user mode (your own machine, tests)
        raise RuntimeError("No workspace selected for this request")
    return wid


def set_current(wid: int | None):
    return _current.set(wid)


@contextmanager
def use(wid: int):
    token = _current.set(wid)
    try:
        yield
    finally:
        _current.reset(token)


def of_company(company_id: int) -> int | None:
    with db.session() as s:
        r = s.execute("SELECT workspace_id FROM company WHERE id=?", (company_id,)).fetchone()
    return r["workspace_id"] if r else None


def of_person(person_id: int) -> int | None:
    with db.session() as s:
        r = s.execute("SELECT c.workspace_id FROM person p JOIN company c ON c.id=p.company_id WHERE p.id=?",
                      (person_id,)).fetchone()
    return r["workspace_id"] if r else None
