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
        former = next((p["title"] for p in dupes if p["title"] and FORMER.search(p["title"])), None)
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
    return removed
