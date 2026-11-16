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
            elif cur is True and p.get("current") == 0:
                s.execute("UPDATE person SET current=1, left_note=NULL WHERE id=?", (p["id"],))
            elif p.get("current") == 0 and not p.get("left_note"):
                former += 1   # marked by research ("left" in a document); keep it
    return former
