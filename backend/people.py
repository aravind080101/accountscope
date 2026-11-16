"""One person, one record: match names that differ only in dots, honorifics or word order.

"Dr N Kamakodi" = "Dr. N. Kamakodi" = "N Kamakodi", and "R. Vijay Anandh" = "Vijay Anandh R".
Masked names from Apollo ("Ravi I***") are never merged by name; they match by apollo_id elsewhere.
"""
import re

HONORIFICS = {"dr", "mr", "mrs", "ms", "miss", "shri", "sri", "smt", "prof", "er", "ca", "adv", "capt", "col", "sir"}
FORMER = re.compile(r"\b(upto|up to|until|till|former|ex-|erstwhile|retired)\b", re.I)


def name_key(name: str) -> str | None:
    if not name or "*" in name:
        return None
    tokens = [t for t in re.split(r"[\s.,]+", name.lower()) if t and t not in HONORIFICS]
    if not tokens:
        return None
    long = sorted(t for t in tokens if len(t) > 1)
    # two or more real words: initials can be dropped ("Vijay Anandh" = "R. Vijay Anandh");
    # one real word ("N Kamakodi"): keep the initials so "A Kumar" and "B Kumar" stay apart
    return " ".join(long) if len(long) >= 2 else " ".join(sorted(tokens))


def canonical_name(s, company_id: int, name: str) -> str:
    """The full_name already stored for this person at this company, or the name as given."""
    key = name_key(name)
    if not key:
        return name
    for r in s.execute("SELECT full_name FROM person WHERE company_id=?", (company_id,)):
        if name_key(r["full_name"]) == key:
            return r["full_name"]
    return name


def merge_duplicates(company_id: int) -> int:
    """Fold duplicate people at a company into one record each. Returns how many records were removed."""
    from . import db
    with db.session() as s:
        people = db.rows(s.execute(
            """SELECT p.id, p.full_name, p.title, p.email, p.apollo_id, p.linkedin_url,
                      EXISTS(SELECT 1 FROM buyer_brief b WHERE b.person_id=p.id) has_brief,
                      (SELECT COUNT(*) FROM initiative_contact ic WHERE ic.person_id=p.id) links
               FROM person p WHERE p.company_id=?""", (company_id,)))
    groups: dict[str, list[dict]] = {}
    for p in people:
        k = name_key(p["full_name"])
        if k:
            groups.setdefault(k, []).append(p)
    removed = 0
    for dupes in groups.values():
        if len(dupes) < 2:
            continue
        dupes.sort(key=lambda p: (not p["email"], not p["has_brief"], not p["apollo_id"], -(p["links"] or 0), p["id"]))
        keep, rest = dupes[0], dupes[1:]
        former = next((p["title"] for p in dupes if p["title"] and role_status(p["title"])[0] is False), None)
        dated = next((p["title"] for p in dupes if p["title"] and role_status(p["title"])[0] is True), None)
        with db.session() as s:
            for d in rest:
                for table, other in (("initiative_contact", "initiative_id"), ("project_contact", "project_id")):
                    s.execute(f"""UPDATE {table} SET person_id=? WHERE person_id=? AND {other} NOT IN
                                  (SELECT {other} FROM {table} WHERE person_id=?)""", (keep["id"], d["id"], keep["id"]))
                    s.execute(f"DELETE FROM {table} WHERE person_id=?", (d["id"],))
                for table in ("pitch", "person_sample"):
                    s.execute(f"UPDATE {table} SET person_id=? WHERE person_id=?", (keep["id"], d["id"]))
                if not keep["has_brief"] and d["has_brief"]:
                    s.execute("UPDATE buyer_brief SET person_id=? WHERE person_id=?", (keep["id"], d["id"]))
                    keep["has_brief"] = 1
                s.execute("DELETE FROM buyer_brief WHERE person_id=?", (d["id"],))
                s.execute("""UPDATE person SET email=COALESCE(email, ?), linkedin_url=COALESCE(linkedin_url, ?),
                             apollo_id=COALESCE(apollo_id, ?) WHERE id=?""", (d["email"], d["linkedin_url"], d["apollo_id"], keep["id"]))
                s.execute("UPDATE person SET reports_to=? WHERE reports_to=? AND company_id=?", (keep["full_name"], d["full_name"], company_id))
                s.execute("DELETE FROM person WHERE id=?", (d["id"],))
                removed += 1
            if former:  # someone who has left the role: keep that visible
                s.execute("UPDATE person SET title=? WHERE id=?", (former, keep["id"]))
            elif dated and not role_status(keep["title"] or "")[0]:  # keep the title that says since when
                s.execute("UPDATE person SET title=? WHERE id=?", (dated, keep["id"]))
    return removed


# ------------------------------------------------------------- current or former role

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE = re.compile(r"(\d{1,2})[\s.-]*([A-Za-z]{3,9})[,\s.-]*(\d{4})|([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})|"
                   r"(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})[./](\d{1,2})[./](\d{4})")
_ENDED = re.compile(r"\b(upto|up to|until|till|ceased|stepped down|demitted)\b", re.I)
_PAST = re.compile(r"\b(former|ex-|erstwhile|retired|outgoing)\b", re.I)
_STARTS = re.compile(r"\b(w\.?\s?e\.?\s?f\.?|with effect from|effective|from)\b", re.I)
TOP_ROLES = {"ceo": ("ceo", "chief executive"), "md": ("managing director", "md"), "chair": ("chairman", "chairperson", "chair"),
             "cfo": ("cfo", "chief financial"), "cto": ("cto", "chief technology"), "cio": ("cio", "chief information"),
             "coo": ("coo", "chief operating"), "cro": ("cro", "chief risk")}


def _date_after(title: str, at: int):
    from datetime import date
    m = _DATE.search(title, at)
    if not m:
        return None
    g = m.groups()
    try:
        if g[0]:
            return date(int(g[2]), _MONTHS[g[1][:3].lower()], int(g[0]))
        if g[3]:
            return date(int(g[5]), _MONTHS[g[3][:3].lower()], int(g[4]))
        if g[6]:
            return date(int(g[6]), int(g[7]), int(g[8]))
        return date(int(g[11]), int(g[10]), int(g[9]))
    except (KeyError, ValueError):
        return None


def role_status(title: str, today=None):
    """(False, note) if the title shows they've left or not yet started; (True, note) if it shows a start date that
    has passed; (None, None) if the title doesn't say."""
    from datetime import date
    today = today or date.today()
    t = title or ""
    m = _ENDED.search(t)
    if m:
        d = _date_after(t, m.end())
        if d is None or d < today:
            return False, f"Left the role{' on ' + d.strftime('%d %b %Y') if d else ''}"
    if _PAST.search(t):
        return False, "Former holder of this role"
    m = _STARTS.search(t)
    if m:
        d = _date_after(t, m.end())
        if d and d > today:
            return False, f"Takes over on {d.strftime('%d %b %Y')}"
        if d:
            return True, f"In the role since {d.strftime('%d %b %Y')}"
    return None, None


def _top_roles(title: str) -> set[str]:
    t = f" {(title or '').lower()} "
    return {k for k, words in TOP_ROLES.items() if any(re.search(rf"\b{re.escape(w)}\b", t) for w in words)}


def refresh_status(company_id: int, today=None) -> int:
    """Mark people who have left (or not yet started) their role, from their titles and from succession:
    if someone holds a top role 'w.e.f.' a past date, earlier holders of that role without a date are former.
    Returns how many people are marked former."""
    from . import db
    with db.session() as s:
        people = db.rows(s.execute("SELECT id, full_name, title, current, left_note FROM person WHERE company_id=?", (company_id,)))
    status = {}
    successors = {}   # role -> (start date note, name) for people whose title shows they took over
    for p in people:
        cur, note = role_status(p["title"], today)
        status[p["id"]] = (cur, note)
        if cur is True:
            for r in _top_roles(p["title"]):
                successors[r] = p
    for p in people:
        cur, note = status[p["id"]]
        if cur is None and p.get("current") != 0:
            for r in _top_roles(p["title"]) & set(successors):
                succ = successors[r]
                if succ["id"] != p["id"] and name_key(succ["full_name"]) != name_key(p["full_name"]):
                    cur, note = False, f"Succeeded by {succ['full_name']}"
                    break
        status[p["id"]] = (cur, note)
    former = 0
    with db.session() as s:
        for p in people:
            cur, note = status[p["id"]]
            if cur is False:
                former += 1
                if p.get("current") != 0 or p.get("left_note") != note:
                    s.execute("UPDATE person SET current=0, left_note=? WHERE id=?", (note, p["id"]))
            elif cur is True and p.get("current") == 0 and not (p.get("left_note") or "").startswith("Leadership check"):
                s.execute("UPDATE person SET current=1, left_note=NULL WHERE id=?", (p["id"],))
            elif p.get("current") == 0 and not p.get("left_note"):
                former += 1   # marked by research ("left" in a document); keep it
    return former


# ------------------------------------------------------------- who holds each top role today (any company)

LEADERSHIP_SYSTEM = """You verify a company's CURRENT leadership as of today's date, from recent sources only.
Sources often disagree because older articles name people who have since moved on. Prefer the most recent dated
source, the company's own leadership or board page, stock-exchange filings and appointment announcements.
An appointment that takes effect on a date that has passed means that person holds the role now and the previous
holder does not. Never guess: if the sources don't settle a role, leave it out."""

LEADERSHIP_ROLES = ["CEO", "Managing Director", "Chairman", "CFO", "CTO", "CIO", "COO", "Chief Risk Officer", "Chief Digital Officer"]


def leadership_queries(name: str, domain: str | None) -> list[tuple[str, dict]]:
    q = [(f'"{name}" CEO OR "managing director" appointed OR "takes charge" OR "steps down" OR succeeds', {"topic": "news", "days": 540}),
         (f'"{name}" leadership team board of directors', {})]
    if domain:
        q.append((f"{name} leadership management team board", {"include_domains": [domain]}))
    return q


def verify_leadership(company: dict, today=None, log=lambda m: None) -> dict:
    """Search recent sources for who holds each top role now, then mark anyone in our list who no longer does.
    Works for any company. Returns {"current": [...], "former": [...], "changed": n}."""
    from datetime import date
    from . import config, db, llm
    from .providers import tavily
    today = today or date.today()
    if not (config.TAVILY_API_KEY and llm.available()):
        return {"current": [], "former": [], "changed": 0}
    docs, seen = [], set()
    for q, opts in leadership_queries(company["name"], company.get("domain")):
        try:
            for r in tavily.raw_search(q, max_results=6, **opts):
                if r["url"] not in seen and r.get("text"):
                    seen.add(r["url"])
                    docs.append(r)
        except Exception:
            continue
    if not docs:
        return {"current": [], "former": [], "changed": 0}
    with db.session() as s:
        ours = db.rows(s.execute("SELECT id, full_name, title, current FROM person WHERE company_id=?", (company["id"],)))
    listing = "\n\n".join(f"[{i}] {d.get('published_at') or 'undated'} | {d['title']}\n{d['url']}\n{d['text'][:1800]}"
                          for i, d in enumerate(docs[:14]))
    people_list = "\n".join(f"- {p['full_name']}: {p['title']}" for p in ours) or "- none"
    out = llm.complete_json(LEADERSHIP_SYSTEM, f"""Company: {company['name']}{' (' + company['domain'] + ')' if company.get('domain') else ''}
Today: {today.isoformat()}

PEOPLE WE HAVE ON FILE (titles may be out of date):
{people_list}

RECENT SOURCES:
{listing}

Return {{"current": [{{"role": one of {LEADERSHIP_ROLES}, "name": full name, "since": "YYYY-MM-DD" or null,
  "source": source number}}],
"former": [{{"name": a person ON FILE who no longer holds the role their title shows, "role": that role,
  "reason": one line, e.g. "Succeeded by X on 1 May 2026" or "Retired in March 2026", "source": source number}}]}}
Only include what the sources clearly support.""", 1800)
    current = [c for c in (out.get("current") or []) if isinstance(c, dict) and c.get("name") and isinstance(c.get("source"), int)]
    former = [f for f in (out.get("former") or []) if isinstance(f, dict) and f.get("name") and isinstance(f.get("source"), int)]
    by_key = {}
    for p in ours:
        k = name_key(p["full_name"])
        if k:
            by_key.setdefault(k, []).append(p)
    current_keys = {name_key(c["name"]) for c in current}
    changed = 0
    with db.session() as s:
        for f in former:
            k = name_key(f["name"])
            if not k or k in current_keys:   # never retire someone the same check says is current
                continue
            for p in by_key.get(k, []):
                src = docs[f["source"]]["url"] if 0 <= f["source"] < len(docs) else ""
                note = "Leadership check: " + (f.get("reason") or "no longer in this role")[:160] + (f" ({src})" if src else "")
                s.execute("UPDATE person SET current=0, left_note=? WHERE id=?", (note, p["id"]))
                changed += 1
        for c in current:
            for p in by_key.get(name_key(c["name"]), []):
                if p.get("current") == 0:   # a newer source says they hold a top role now
                    s.execute("UPDATE person SET current=1, left_note=NULL WHERE id=?", (p["id"],))
                    changed += 1
    log(f"Leadership check: {len(current)} current role holder(s) confirmed from {len(docs)} recent source(s)"
        + (f"; {changed} person record(s) updated" if changed else ""))
    return {"current": current, "former": former, "changed": changed}
