"""Feedback loop. Your team confirms or rejects contacts and dismisses initiatives.

- A rejected person is never suggested again for that company and initiative type.
- A confirmed person is pinned to the top on every future run.
- Every verdict also updates title_stats, so across ALL companies the scoring learns which
  titles really turn out to be the right contact for each kind of initiative (learning stays inside
  each workspace; one client's verdicts never shape another's results).
- Dismissed initiatives are skipped in future research of that company.
"""
import re

from . import db, tenancy

_STOP = {"the", "a", "an", "of", "and", "to", "for", "new", "programme", "program", "initiative", "project"}


def title_key(title: str) -> str:
    words = sorted({w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if w not in {"of", "the", "and", "for", "-"}})
    return " ".join(words)


def _name_tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if t not in _STOP}


def same_initiative(a: str, b: str) -> bool:
    x, y = _name_tokens(a), _name_tokens(b)
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= 0.5


def record_contact(icid: int, verdict: str) -> dict:
    if verdict not in ("confirmed", "rejected", "clear"):
        raise ValueError("verdict must be confirmed, rejected or clear")
    with db.session() as s:
        row = s.execute(
            """SELECT ic.id, ic.feedback old, p.full_name, p.title, i.name init_name, i.category, i.company_id
               FROM initiative_contact ic JOIN person p ON p.id=ic.person_id JOIN initiative i ON i.id=ic.initiative_id
               WHERE ic.id=?""", (icid,)).fetchone()
        if not row:
            raise LookupError("Contact not found")
        r = dict(row)
        tk = title_key(r["title"])
        # Undo the previous verdict's effect on the title statistics.
        if r["old"] in ("confirmed", "rejected"):
            col = "confirms" if r["old"] == "confirmed" else "rejects"
            s.execute(f"UPDATE title_stats SET {col}=MAX(0, {col}-1) WHERE workspace_id=? AND category=? AND title_key=?",
                      (tenancy.current(), r["category"], tk))
            s.execute("""DELETE FROM feedback WHERE target='contact' AND company_id=? AND lower(person_name)=lower(?)
                         AND category=?""", (r["company_id"], r["full_name"], r["category"]))
        new = None if verdict == "clear" else verdict
        s.execute("UPDATE initiative_contact SET feedback=? WHERE id=?", (new, icid))
        if new:
            s.execute("""INSERT INTO feedback(workspace_id, company_id, target, person_name, title, initiative_name, category, verdict)
                         VALUES (?, ?, 'contact', ?, ?, ?, ?, ?)""",
                      (tenancy.current(), r["company_id"], r["full_name"], r["title"], r["init_name"], r["category"], new))
            col = "confirms" if new == "confirmed" else "rejects"
            s.execute(f"""INSERT INTO title_stats(workspace_id, category, title_key, {col}) VALUES (?,?,?,1)
                          ON CONFLICT(workspace_id, category, title_key) DO UPDATE SET {col}={col}+1""",
                      (tenancy.current(), r["category"], tk))
    return {"id": icid, "feedback": new}


def record_initiative(iid: int, verdict: str) -> dict:
    if verdict not in ("confirmed", "dismissed", "clear"):
        raise ValueError("verdict must be confirmed, dismissed or clear")
    with db.session() as s:
        row = s.execute("SELECT id, name, category, company_id FROM initiative WHERE id=?", (iid,)).fetchone()
        if not row:
            raise LookupError("Initiative not found")
        r = dict(row)
        s.execute("DELETE FROM feedback WHERE target='initiative' AND company_id=? AND initiative_name=?",
                  (r["company_id"], r["name"]))
        new = None if verdict == "clear" else verdict
        s.execute("UPDATE initiative SET feedback=? WHERE id=?", (new, iid))
        if new:
            s.execute("""INSERT INTO feedback(workspace_id, company_id, target, initiative_name, category, verdict)
                         VALUES (?, ?, 'initiative', ?, ?, ?)""", (tenancy.current(), r["company_id"], r["name"], r["category"], new))
    return {"id": iid, "feedback": new}


def for_company(company_id: int) -> dict:
    """Everything the pipeline needs to respect past feedback for one company."""
    with db.session() as s:
        rows = db.rows(s.execute("SELECT * FROM feedback WHERE company_id=? ORDER BY id", (company_id,)))
    people, inits = {}, []
    for r in rows:
        if r["target"] == "contact":
            people[(r["person_name"].lower(), r["category"])] = r["verdict"]
        else:
            inits.append((r["initiative_name"], r["verdict"]))
    return {"people": people, "initiatives": inits}


def initiative_verdict(fb: dict, name: str) -> str | None:
    verdict = None
    for n, v in fb["initiatives"]:
        if same_initiative(n, name):
            verdict = v
    return verdict


def title_adjustment(cat: str, title: str) -> float:
    """-0.15 .. +0.15 based on how often this title was confirmed vs rejected for this initiative type."""
    with db.session() as s:
        r = s.execute("SELECT confirms, rejects FROM title_stats WHERE workspace_id=? AND category=? AND title_key=?",
                      (tenancy.current(), cat, title_key(title))).fetchone()
    if not r or (r["confirms"] + r["rejects"]) == 0:
        return 0.0
    return round(0.15 * (r["confirms"] - r["rejects"]) / (r["confirms"] + r["rejects"] + 2), 3)
