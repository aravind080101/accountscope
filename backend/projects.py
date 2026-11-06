"""Projects: named engagements between a company and one specific client or partner.

Different from initiatives (the company's own internal programmes). A project always has a
counterparty: "Infosys -> Aviva: claims platform modernisation" (client: the company delivers it)
or "Zen Finance <- Temenos: core banking go-live" (partner: the counterparty delivers it).

Projects are never deleted by a re-run. New research adds evidence and updates the record;
only "Not relevant" hides one.
"""
import json
import re

from . import db, feedback, llm, profiles
from .providers import apollo

STATUSES = ["announced", "won", "in_progress", "live", "completed"]
_SUFFIX = re.compile(r"\b(ltd|limited|inc|plc|llc|corp|corporation|group|holdings|pvt|private|co|company|the)\b\.?", re.I)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _SUFFIX.sub("", name.lower())).strip()


def _same_counterparty(a: str, b: str) -> bool:
    x, y = _key(a), _key(b)
    return bool(x and y) and (x == y or x.split()[0] == y.split()[0])


def norm_start(value) -> str | None:
    """'2026-09-14', '2026-09', 'Sep 2026', '2026' -> ISO-ish; anything else is kept as written."""
    from datetime import datetime
    from .pipeline import norm_date
    if not value:
        return None
    v = str(value).strip()
    if norm_date(v):
        return norm_date(v)
    for fmt, out in (("%Y-%m", "%Y-%m"), ("%b %Y", "%Y-%m"), ("%B %Y", "%Y-%m"), ("%Y", "%Y")):
        try:
            return datetime.strptime(v, fmt).strftime(out)
        except ValueError:
            pass
    return v[:30]


def merge(cands: list[dict]) -> list[dict]:
    """Group mentions of the same project from different documents."""
    out: list[dict] = []
    for c in cands:
        c = {**c, "counterparty": str(c["counterparty"]).strip(), "name": str(c["name"]).strip()}
        m = next((o for o in out if _same_counterparty(o["counterparty"], c["counterparty"])
                  and (feedback.same_initiative(o["name"], c["name"]) or not o["name"] or not c["name"])), None)
        ev = [{"doc": c.get("doc"), "quote": c.get("quote", "")}] if c.get("doc") else []
        if not m:
            out.append({**c, "evidence": ev, "tech": list(c.get("tech") or []),
                        "company_people": list(c.get("company_people") or []),
                        "counterparty_people": list(c.get("counterparty_people") or []),
                        "owner_titles": list(c.get("owner_titles") or [])})
            continue
        m["evidence"] += ev
        if c.get("relationship") == "same_group":
            m["relationship"] = "same_group"
        for k in ("value", "start", "duration", "direction"):
            m[k] = m.get(k) or c.get(k)
        if c.get("status") in STATUSES and (m.get("status") not in STATUSES or STATUSES.index(c["status"]) > STATUSES.index(m["status"])):
            m["status"] = c["status"]
        if len(c.get("summary") or "") > len(m.get("summary") or ""):
            m["summary"] = c["summary"]
        for k in ("tech", "company_people", "counterparty_people", "owner_titles"):
            m[k] += [x for x in (c.get(k) or []) if x not in m[k]]
    return out


DELIVERY_TITLES = ["Delivery Head", "Delivery Director", "Client Partner", "Account Director", "Engagement Manager",
                   "Program Manager", "Programme Director", "Practice Head", "Head of Delivery"]
BUYER_SIDE_TITLES = ["CIO", "CTO", "VP Engineering", "Head of IT", "Program Manager", "Head of Technology", "Director IT"]


def _delivery_titles(p: dict) -> list[str]:
    """Who usually runs a client engagement (company delivers) vs owns a partner-delivered project."""
    return DELIVERY_TITLES if p.get("direction") == "client" else BUYER_SIDE_TITLES


WEAK_SOURCES = {"jobs"}  # job posts describe a team's work, not a contracted project


def _worked_on(s, pid: int) -> bool:
    return bool(s.execute(
        """SELECT 1 FROM project p WHERE p.id=? AND (p.feedback IS NOT NULL OR EXISTS (SELECT 1 FROM project_contact pc
           JOIN person x ON x.id=pc.person_id WHERE pc.project_id=p.id AND (pc.feedback IS NOT NULL OR x.email IS NOT NULL OR x.phone IS NOT NULL)))""",
        (pid,)).fetchone())


def _delete(s, pid: int) -> None:
    s.execute("DELETE FROM project_contact WHERE project_id=?", (pid,))
    s.execute("DELETE FROM project_evidence WHERE project_id=?", (pid,))
    s.execute("DELETE FROM project WHERE id=?", (pid,))


def _prune_weak(company_id: int) -> None:
    """Remove saved projects that only job posts support, unless you've worked on them."""
    with db.session() as s:
        for r in s.execute("SELECT id FROM project WHERE company_id=?", (company_id,)).fetchall():
            types = {x["source_type"] for x in s.execute(
                "SELECT d.source_type FROM project_evidence e JOIN document d ON d.id=e.document_id WHERE e.project_id=?", (r["id"],))}
            if not (types - WEAK_SOURCES) and not _worked_on(s, r["id"]):
                _delete(s, r["id"])


RECHECK_SYSTEM = """You audit a list of 'projects' saved for a company. A real project is a specific piece of work
between the company and an INDEPENDENT other company (a client engagement or a partner delivering work).
Flag entries where the counterparty is the company's own parent, subsidiary, sister company or the group its
captive/GCC serves, and entries that are just routine team work or a vague client mention."""


def _recheck_saved(company: dict) -> None:
    """Ask the AI to flag saved projects that aren't real client/partner engagements; drop untouched ones."""
    if not llm.available():
        return
    with db.session() as s:
        rows = [dict(r) for r in s.execute("SELECT id, name, counterparty, summary FROM project WHERE company_id=?", (company["id"],))]
        rows = [r for r in rows if not _worked_on(s, r["id"])]
    if not rows:
        return
    listing = "\n".join(f"{r['id']}. {r['name']} | counterparty: {r['counterparty']} | {(r['summary'] or '')[:300]}" for r in rows)
    try:
        out = llm.complete_json(RECHECK_SYSTEM, f"""Company: {company['name']} ({company.get('industry') or ''})
{listing}

Return {{"drop": [{{"id": number, "reason": short reason}}]}} listing only the entries that are NOT real projects.""", 1200)
        drop = {int(d["id"]) for d in (out.get("drop") or []) if isinstance(d, dict) and str(d.get("id", "")).isdigit()}
    except Exception:
        return
    with db.session() as s:
        for r in rows:
            if r["id"] in drop:
                _delete(s, r["id"])


def _find_existing(s, company_id: int, p: dict):
    for r in s.execute("SELECT * FROM project WHERE company_id=?", (company_id,)):
        if _same_counterparty(r["counterparty"], p["counterparty"]) and feedback.same_initiative(r["name"], p["name"]):
            return dict(r)
    return None


def _people(company: dict, p: dict) -> list[tuple[dict, str, float, str]]:
    """(person, role, score, why) at the company for this project: named ones first, then title matches."""
    from .pipeline import _title_matches
    out, seen = [], set()
    for x in p.get("company_people") or []:
        if isinstance(x, dict) and x.get("name") and x["name"].lower() not in seen:
            seen.add(x["name"].lower())
            role = "Runs it" if _title_matches(x.get("title") or "", p["owner_titles"] + _delivery_titles(p)) else "Team"
            out.append(({"full_name": x["name"], "title": x.get("title"), "source": "evidence"}, role, 0.9,
                        f"Named in the source: {x.get('involvement') or 'on this project'}."))
    if company.get("domain"):
        titles = list(dict.fromkeys((p.get("owner_titles") or []) + _delivery_titles(p)))
        for f in apollo.search_people(company["domain"], titles, per_page=15):
            if f["full_name"].lower() in seen:
                continue
            if _title_matches(f["title"], p.get("owner_titles") or []):
                out.append(({**f, "source": "apollo"}, "Runs it", 0.7, f"Title matches who usually runs this engagement ({f['title']})."))
            elif _title_matches(f["title"], _delivery_titles(p)):
                out.append(({**f, "source": "apollo"}, "Sponsor", 0.55,
                            f"{'Delivery' if p.get('direction') == 'client' else 'Technology'} leader; likely involved. Not named in sources."))
            else:
                continue
            seen.add(f["full_name"].lower())
    out.sort(key=lambda t: -t[2])
    return out[:5]


def save(company: dict, cands: list[dict], key_to_id: dict, docs_by_key: dict, profile: dict) -> tuple[int, int]:
    """Upsert this run's projects. Returns (projects found this run, new ones)."""
    from .pipeline import norm_date
    found = merge(cands)
    for p in found:
        p["summary"] = p.get("summary") or ""
        p["tech"] = [t for t in p["tech"] if isinstance(t, str)][:15]
        p["owner_titles"] = [t for t in p["owner_titles"] if isinstance(t, str)][:5]
        p["direction"] = p.get("direction") if p.get("direction") in ("client", "partner") else "client"
        p["status"] = p.get("status") if p.get("status") in STATUSES else "announced"
    # A project needs an outside counterparty and a source beyond job posts (deal news, case study, press release).
    rejected = [p for p in found if p.get("relationship") == "same_group"
                or _same_counterparty(p["counterparty"], company["name"])
                or not any(docs_by_key[e["doc"]]["source_type"] not in WEAK_SOURCES
                           for e in p["evidence"] if e.get("doc") in docs_by_key)]
    found = [p for p in found if p not in rejected]
    with db.session() as s:
        for p in rejected:  # drop earlier saves of these unless you've worked on them
            old = _find_existing(s, company["id"], p)
            if old and not _worked_on(s, old["id"]):
                _delete(s, old["id"])
    _prune_weak(company["id"])
    _recheck_saved(company)
    if not found:
        return 0, 0
    fits = profiles.fit_many(profile, company, [
        {"name": f"{p['name']} ({'for client' if p['direction'] == 'client' else 'delivered by partner'} {p['counterparty']})",
         "summary": p["summary"], "tech": p["tech"], "stage": p["status"]} for p in found])
    new = 0
    cid = company["id"]
    for p, (fit, why) in zip(found, fits):
        ev = [e for e in p["evidence"] if e.get("doc") in key_to_id]
        dates = sorted(d for d in (norm_date(docs_by_key[e["doc"]].get("published_at")) for e in ev) if d)
        with db.session() as s:
            old = _find_existing(s, cid, p)
            if old:
                if old.get("feedback") == "dismissed":
                    continue
                s.execute(
                    """UPDATE project SET direction=?, status=?, summary=CASE WHEN LENGTH(?)>LENGTH(COALESCE(summary,'')) THEN ? ELSE summary END,
                       tech=?, value=COALESCE(?, value), start_date=COALESCE(?, start_date), duration=COALESCE(?, duration),
                       counterparty_people=?, owner_titles=?, last_seen=MAX(COALESCE(last_seen,''), COALESCE(?,'')),
                       first_seen=COALESCE(first_seen, ?), fit_score=?, fit_reason=? WHERE id=?""",
                    (p["direction"], p["status"], p["summary"], p["summary"],
                     json.dumps(sorted(set(json.loads(old["tech"] or "[]")) | set(p["tech"]))),
                     p.get("value"), norm_start(p.get("start")), p.get("duration"),
                     json.dumps(p["counterparty_people"][:6]), json.dumps(p["owner_titles"]),
                     max(dates, default=None), min(dates, default=None), fit, why, old["id"]))
                pid = old["id"]
            else:
                pid = s.execute(
                    """INSERT INTO project(company_id, name, counterparty, direction, status, summary, tech, value, start_date,
                       duration, counterparty_people, owner_titles, first_seen, last_seen, fit_score, fit_reason)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, p["name"], p["counterparty"], p["direction"], p["status"], p["summary"], json.dumps(p["tech"]),
                     p.get("value"), norm_start(p.get("start")), p.get("duration"), json.dumps(p["counterparty_people"][:6]),
                     json.dumps(p["owner_titles"]), min(dates, default=None), max(dates, default=None), fit, why)).lastrowid
                new += 1
                if company.get("last_researched_at"):  # not the first research: it's a change worth an alert
                    s.execute("INSERT INTO alert(company_id, kind, title, detail) VALUES (?,?,?,?)",
                              (cid, "new_project", f"New project: {p['name']} with {p['counterparty']}", p["summary"]))
            for e in ev:
                s.execute("INSERT OR IGNORE INTO project_evidence(project_id, document_id, quote) VALUES (?,?,?)",
                          (pid, key_to_id[e["doc"]], e.get("quote", "")))
            # refresh untouched suggestions; keep contacts you enriched or reviewed
            s.execute("""DELETE FROM project_contact WHERE project_id=? AND (feedback='rejected' OR (feedback IS NULL AND person_id IN
                         (SELECT id FROM person WHERE email IS NULL AND phone IS NULL)))""", (pid,))
        _save_contacts(cid, pid, _people(company, p))
    return len(found), new


def _save_contacts(company_id: int, pid: int, people: list) -> None:
    with db.session() as s:
        rejected = {r["person_id"] for r in s.execute("SELECT person_id FROM project_contact WHERE project_id=? AND feedback='rejected'", (pid,))}
        for person, role, score, why in people:
            same = person.get("apollo_id") and s.execute(
                "SELECT full_name FROM person WHERE company_id=? AND apollo_id=?", (company_id, person["apollo_id"])).fetchone()
            name = same["full_name"] if same else person["full_name"]
            s.execute(
                """INSERT INTO person(company_id, full_name, title, seniority, linkedin_url, apollo_id, source) VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(company_id, full_name) DO UPDATE SET title=COALESCE(excluded.title, title),
                   apollo_id=COALESCE(excluded.apollo_id, apollo_id), linkedin_url=COALESCE(excluded.linkedin_url, linkedin_url)""",
                (company_id, name, person.get("title"), person.get("seniority"), person.get("linkedin_url"),
                 person.get("apollo_id"), person["source"]))
            person_id = s.execute("SELECT id FROM person WHERE company_id=? AND full_name=?", (company_id, name)).fetchone()["id"]
            if person_id in rejected:
                continue
            s.execute(
                """INSERT INTO project_contact(project_id, person_id, role, score, rationale, source) VALUES (?,?,?,?,?,?)
                   ON CONFLICT(project_id, person_id) DO UPDATE SET role=excluded.role, score=MAX(score, excluded.score),
                   rationale=excluded.rationale""", (pid, person_id, role, score, why, person["source"]))


def for_company(company_id: int) -> list[dict]:
    with db.session() as s:
        rows = db.rows(s.execute(
            """SELECT * FROM project WHERE company_id=? AND COALESCE(feedback,'')!='dismissed'
               ORDER BY feedback='confirmed' DESC, fit_score DESC, COALESCE(last_seen, first_seen) DESC""", (company_id,)))
        for r in rows:
            for k in ("tech", "counterparty_people", "owner_titles"):
                r[k] = json.loads(r[k] or "[]")
            r["evidence"] = db.rows(s.execute(
                """SELECT d.source_type, d.url, d.title, d.published_at, e.quote FROM project_evidence e
                   JOIN document d ON d.id=e.document_id WHERE e.project_id=? ORDER BY d.published_at DESC""", (r["id"],)))
            r["contacts"] = db.rows(s.execute(
                """SELECT pc.id, pc.role, pc.score, pc.rationale, pc.feedback, pc.source, p.id person_id, p.full_name, p.title,
                   p.email, p.phone, p.linkedin_url, (SELECT 1 FROM buyer_brief b WHERE b.person_id=p.id) has_brief
                   FROM project_contact pc JOIN person p ON p.id=pc.person_id
                   WHERE pc.project_id=? AND COALESCE(pc.feedback,'')!='rejected' ORDER BY pc.feedback='confirmed' DESC, pc.score DESC""",
                (r["id"],)))
            acct = s.execute("SELECT id FROM company WHERE workspace_id=(SELECT workspace_id FROM company WHERE id=?) AND LOWER(name)=LOWER(?)",
                             (company_id, r["counterparty"])).fetchone()
            r["counterparty_account_id"] = acct["id"] if acct else None
    return rows
