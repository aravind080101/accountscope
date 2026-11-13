"""Likely org chart for one company.

Reporting lines come from two places, and every edge says which:
- confirmed: a source said so ("reporting to the Director of QA" in a job post)
- inferred:  same function, next level up by seniority, else the function's C-level, else the CEO
"""
import re

from . import db

FUNCTIONS = [  # checked in order; first match wins
    ("Quality", {"qa", "quality", "test", "testing", "sdet"}),
    ("Security & risk", {"security", "ciso", "risk", "compliance", "appsec", "cyber"}),
    ("Data & AI", {"data", "ai", "ml", "analytics", "science", "cdao"}),
    ("Product & digital", {"product", "digital", "channels", "design", "ux", "experience", "cpo", "cdo", "mobile"}),
    ("IT", {"cio", "it", "information", "applications", "erp", "sap", "infrastructure"}),
    ("Engineering", {"engineering", "engineer", "software", "technology", "cto", "platform", "devops", "sre",
                     "architect", "cloud", "development", "developer"}),
]
FUNCTION_HEADS = {  # which C-level a function usually rolls up to
    "Quality": ["cto", "vp engineering", "cio"], "Engineering": ["cto", "cio"], "Data & AI": ["chief data officer", "cto", "cio"],
    "Product & digital": ["cpo", "cdo", "chief digital officer", "chief product officer", "cto"], "IT": ["cio", "cto"],
    "Security & risk": ["ciso", "cio", "chief risk officer"], "Business": ["ceo"],
}
_ALIASES = {"chief technology officer": "cto", "chief information officer": "cio", "chief executive officer": "ceo",
            "chief information security officer": "ciso", "chief product officer": "cpo", "chief digital officer": "cdo",
            "chief operating officer": "coo", "vice president": "vp", "quality assurance": "qa"}


def _words(title: str) -> set[str]:
    t = (title or "").lower()
    for long, short in _ALIASES.items():
        t = t.replace(long, short)
    return set(re.findall(r"[a-z0-9]+", t))


def function_of(title: str) -> str:
    w = _words(title)
    if w & {"ceo", "founder", "md", "coo", "cfo", "president"} and not w & {"vp"}:
        return "Business"
    for name, keys in FUNCTIONS:
        if w & keys:
            return name
    return "Business"


def rank_of(title: str) -> int:
    """0 = CEO ... 7 = individual contributor."""
    w = _words(title)
    t = (title or "").lower()
    if w & {"ceo", "founder", "md"} or "managing director" in t:
        return 0
    if w & {"cto", "cio", "coo", "cfo", "cdo", "cpo", "ciso"} or "chief" in w:
        return 1
    if w & {"president", "evp", "svp", "vp"}:
        return 2
    if "head" in w:
        return 3
    if "director" in w:
        return 4
    if "manager" in w:
        return 5
    if w & {"lead", "principal", "architect", "senior"}:
        return 6
    return 7


def _match_manager(ref: str, people: list[dict], me: dict) -> dict | None:
    """Resolve 'reports to X' by name first, then by title."""
    if not ref:
        return None
    ref_l = ref.lower().strip()
    for p in people:
        if p is not me and p["full_name"].lower() == ref_l:
            return p
    rw = _words(ref) - {"the", "of", "and"}
    best = None
    for p in people:
        if p is me or not rw:
            continue
        if rw <= _words(p["title"]) and (best is None or p["rank"] < best["rank"]):
            best = p
    return best


def build(company_id: int) -> dict:
    with db.session() as s:
        people = db.rows(s.execute(
            """SELECT p.id, full_name, title, seniority, source, reports_to, reports_to_source, linkedin_url, email,
                      EXISTS(SELECT 1 FROM buyer_brief b WHERE b.person_id=p.id) has_brief FROM person p WHERE company_id=?""",
            (company_id,)))
        links = db.rows(s.execute(
            """SELECT ic.person_id, ic.role, ic.feedback, i.id initiative_id, i.name initiative FROM initiative_contact ic
               JOIN initiative i ON i.id=ic.initiative_id WHERE i.company_id=? AND COALESCE(i.feedback,'')!='dismissed'""",
            (company_id,)))
    rejected = {(l["person_id"]) for l in links if l["feedback"] == "rejected"}
    people = [p for p in people if p["id"] not in rejected or any(l["person_id"] == p["id"] and l["feedback"] != "rejected" for l in links)]
    for p in people:
        p["function"] = function_of(p["title"])
        p["rank"] = rank_of(p["title"])
        p["initiatives"] = [{"id": l["initiative_id"], "name": l["initiative"], "role": l["role"]}
                            for l in links if l["person_id"] == p["id"] and l["feedback"] != "rejected"]

    ceo = min((p for p in people if p["rank"] == 0), key=lambda p: p["id"], default=None)
    edges = []
    for p in people:
        if p is ceo:
            continue
        mgr = _match_manager(p.get("reports_to") or "", people, p)
        kind = "confirmed" if mgr and p.get("reports_to_source") == "evidence" else "inferred"
        if mgr and mgr["rank"] >= p["rank"] and kind == "inferred":
            mgr = None
        if not mgr:
            kind = "inferred"
            above = [q for q in people if q is not p and q["function"] == p["function"] and q["rank"] < p["rank"] and q["rank"] >= 1]
            if above:
                mgr = max(above, key=lambda q: (q["rank"], -q["id"]))
            else:
                for head in FUNCTION_HEADS.get(p["function"], []):
                    hw = _words(head)
                    cand = [q for q in people if q is not p and q["rank"] < p["rank"] and hw <= _words(q["title"])]
                    if cand:
                        mgr = cand[0]
                        break
            if not mgr and ceo and p["rank"] > 0:
                mgr = ceo
        if mgr:
            edges.append({"from": mgr["id"], "to": p["id"], "kind": kind})

    nodes = [{"id": p["id"], "name": p["full_name"], "title": p["title"], "function": p["function"], "rank": p["rank"],
              "source": p["source"], "linkedin_url": p["linkedin_url"], "email": p.get("email"),
              "has_brief": bool(p.get("has_brief")), "initiatives": p["initiatives"]} for p in people]
    nodes.sort(key=lambda n: (n["rank"], n["function"], n["name"]))
    return {"nodes": nodes, "edges": edges,
            "confirmed": sum(e["kind"] == "confirmed" for e in edges), "inferred": sum(e["kind"] == "inferred" for e in edges)}
