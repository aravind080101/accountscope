"""Ownership checks: an id from the URL must belong to the caller's workspace, or the API answers 404.

404 (not 403) so one client can't even learn that another client's account exists.
"""
from fastapi import HTTPException

from . import db, tenancy

_SQL = {
    "company": "SELECT workspace_id FROM company WHERE id=?",
    "person": "SELECT c.workspace_id FROM person p JOIN company c ON c.id=p.company_id WHERE p.id=?",
    "initiative": "SELECT c.workspace_id FROM initiative i JOIN company c ON c.id=i.company_id WHERE i.id=?",
    "contact": """SELECT c.workspace_id FROM initiative_contact ic JOIN initiative i ON i.id=ic.initiative_id
                  JOIN company c ON c.id=i.company_id WHERE ic.id=?""",
    "project": "SELECT c.workspace_id FROM project p JOIN company c ON c.id=p.company_id WHERE p.id=?",
    "project_contact": """SELECT c.workspace_id FROM project_contact pc JOIN project p ON p.id=pc.project_id
                          JOIN company c ON c.id=p.company_id WHERE pc.id=?""",
    "pitch": """SELECT c.workspace_id FROM pitch pt JOIN person p ON p.id=pt.person_id
                JOIN company c ON c.id=p.company_id WHERE pt.id=?""",
    "sample": """SELECT c.workspace_id FROM person_sample x JOIN person p ON p.id=x.person_id
                 JOIN company c ON c.id=p.company_id WHERE x.id=?""",
    "run": "SELECT c.workspace_id FROM run r JOIN company c ON c.id=r.company_id WHERE r.id=?",
    "alert": "SELECT c.workspace_id FROM alert a JOIN company c ON c.id=a.company_id WHERE a.id=?",
}
_LABEL = {"company": "Account", "person": "Person", "initiative": "Initiative", "contact": "Contact", "project": "Project",
          "project_contact": "Contact", "pitch": "Pitch", "sample": "Sample", "run": "Run", "alert": "Alert"}


def check(kind: str, obj_id: int) -> None:
    with db.session() as s:
        r = s.execute(_SQL[kind], (obj_id,)).fetchone()
    if not r or r["workspace_id"] != tenancy.current():
        raise HTTPException(404, f"{_LABEL[kind]} not found")


def owned_ids(kind: str, ids: list[int]) -> list[int]:
    out = []
    for i in ids:
        try:
            check(kind, i)
            out.append(i)
        except HTTPException:
            continue
    return out


company = lambda i: check("company", i)  # noqa: E731
person = lambda i: check("person", i)  # noqa: E731
initiative = lambda i: check("initiative", i)  # noqa: E731
contact = lambda i: check("contact", i)  # noqa: E731
project = lambda i: check("project", i)  # noqa: E731
project_contact = lambda i: check("project_contact", i)  # noqa: E731
pitch = lambda i: check("pitch", i)  # noqa: E731
sample = lambda i: check("sample", i)  # noqa: E731
run = lambda i: check("run", i)  # noqa: E731
