"""The research pipeline for one account.

    collect (full pages, job boards, careers site; cached)  ->  extract initiatives, vendors, tech,
    reporting lines  ->  cluster  ->  apply feedback  ->  find people  ->  score & rank  ->  save
    ->  diff against the previous run and raise alerts

Uses Tavily (search), an LLM - Claude or GPT - (extraction, company profile, openers), Apollo
(people) and optionally BuiltWith (website tech stack).
"""
import json
import re
from datetime import datetime, timedelta, timezone

from . import alerts, config, db, feedback, llm, profiles, projects, tenancy
from .providers import apollo, builtwith, tavily, webtech
from .taxonomy import CATEGORIES, STAGES, category

MAX_DOCS_ANALYSED = 40

# ---------------------------------------------------------------- collect


def collect(company: dict) -> list[dict]:
    return tavily.search(company["name"], company.get("domain"))


def norm_date(value) -> str | None:
    """Any date format the sources use (ISO, 'Mon, 20 Oct 2026 10:00:00 GMT', ...) -> 'YYYY-MM-DD' or None."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(v).strftime("%Y-%m-%d")
    except (TypeError, ValueError, IndexError):
        pass
    for fmt in ("%d %B %Y", "%B %d, %Y", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
    return m.group(1) if m else None


def _clean_list(items) -> list[str]:
    return sorted({str(t).strip() for t in (items or []) if t and str(t).strip()})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def save_documents(company_id: int, docs: list[dict]) -> None:
    with db.session() as s:
        for d in docs:
            s.execute(
                """INSERT INTO document(company_id, source_type, url, title, published_at, text, fetched_at)
                   VALUES (?,?,?,?,?,?,?) ON CONFLICT(company_id, url) DO UPDATE SET
                   text=CASE WHEN length(excluded.text) > length(text) THEN excluded.text ELSE text END,
                   fetched_at=excluded.fetched_at""",
                (company_id, d["source_type"], d["url"], d.get("title"), norm_date(d.get("published_at")), d["text"], _now()),
            )


def stored_documents(company_id: int) -> list[dict]:
    """Every stored source for the company inside the look-back window, newest first."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    with db.session() as s:  # repair dates saved by older versions in other formats
        for r in s.execute("SELECT id, published_at FROM document WHERE company_id=? AND published_at IS NOT NULL", (company_id,)).fetchall():
            fixed = norm_date(r["published_at"])
            if fixed != r["published_at"]:
                s.execute("UPDATE document SET published_at=? WHERE id=?", (fixed, r["id"]))
    with db.session() as s:
        docs = db.rows(s.execute(
            """SELECT id, source_type, url, title, published_at, text FROM document WHERE company_id=?
               AND COALESCE(published_at, fetched_at, '9999') >= ? ORDER BY COALESCE(published_at, fetched_at) DESC""",
            (company_id, cutoff)))
    for d in docs:
        d["key"] = f"doc{d['id']}"
    return docs[:MAX_DOCS_ANALYSED]


def sources_fresh(company: dict) -> bool:
    if not company.get("last_researched_at"):
        return False
    last = datetime.fromisoformat(company["last_researched_at"]).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last < timedelta(hours=config.SOURCE_CACHE_HOURS)


# ---------------------------------------------------------------- extract

EXTRACT_SYSTEM = """You are an account-intelligence analyst for IT services and consulting sellers.
From public documents about ONE company, identify the INITIATIVES it is running or planning: programmes,
launches, migrations, platform builds, rollouts, modernisations, new centres.

An initiative is the underlying piece of work, not a signal about it. A job post is NOT an initiative: it is
evidence of one. "Hiring a Senior QA Engineer for Snowflake ETL testing" is evidence of an initiative like
"Snowflake data platform build-out". Name the work ("Claims platform migration to Guidewire"), never the
hiring ("QA engineering hiring"). Several job posts about the same work belong to ONE initiative.

Separately, identify PROJECTS: named pieces of work between this company and ONE specific other company,
such as a client engagement it won or delivered, or work a named partner is doing for it. A project always
has a named counterparty ("Infosys modernises Aviva's claims platform", "Zen Finance and Temenos core banking go-live").
Internal programmes with no named counterparty are initiatives, not projects. NOT projects:
- work for its own parent, subsidiary or sister company, or a captive/GCC supporting its group
  (e.g. Carelon Global Solutions supporting Elevance Health); mark these relationship "same_group";
- a team's routine day-to-day work described only in a job post or an employee's profile;
- generic "we serve clients like X" logo lists with no specific piece of work.

Only report what the documents support. Never invent people; only list people named in the text."""

CONSOLIDATE_SYSTEM = """You group clues about one company into a clean list of distinct initiatives.
Merge candidates that are the same underlying work, even if named differently. A candidate that is only
a job opening must be merged into the initiative it serves; if no such initiative exists, keep it as an initiative
named after the work it implies (never after the hiring itself)."""


EVIDENCE_TYPES_ANNOUNCED = {"project", "news", "vendor", "filing", "blog", "case_study", "post", "tech", "deal", "footprint"}
LOCATION_TYPES = ["hq", "office", "rd_centre", "engineering_centre", "gcc", "delivery_centre", "plant", "other"]


def consolidate(company: dict, cands: list[dict]) -> list[dict]:
    """Second pass: let the LLM merge candidates into distinct projects. Falls back to name clustering."""
    if len(cands) < 2:
        return cluster(cands)
    listing = "\n".join(
        f"[{i}] {c['name']} ({c['category']}, {c['stage']}): {c.get('summary', '')[:300]} | tech: {', '.join(c.get('tech', [])[:8])}"
        for i, c in enumerate(cands))
    prompt = f"""Company: {company['name']}
Candidate initiatives found in different documents:
{listing}

Return {{"projects": [{{"name": name of the underlying work, "category": one of {list(CATEGORIES)},
"stage": one of {STAGES}, "summary": 1-2 sentences combining the facts,
"owner_titles": [2-5 job titles at {company['name']} who would most likely own or decide this specific work],
"members": [candidate numbers]}}]}}.
Every candidate number must appear in exactly one initiative's members."""
    try:
        out = llm.complete_json(CONSOLIDATE_SYSTEM, prompt, 3000).get("projects")
        if not isinstance(out, list) or not out:
            raise ValueError("no projects")
    except Exception:
        return cluster(cands)
    used, projects = set(), []
    for p in out:
        members = [m for m in p.get("members", []) if isinstance(m, int) and 0 <= m < len(cands) and m not in used]
        if not members:
            continue
        used.update(members)
        group = [cands[m] for m in members]
        stage = p.get("stage") if p.get("stage") in STAGES else max(
            (g["stage"] if g.get("stage") in STAGES else "hinted" for g in group), key=STAGES.index)
        merged = {
            "name": p.get("name") or group[0]["name"],
            "category": p.get("category") if p.get("category") in CATEGORIES else group[0]["category"],
            "stage": stage,
            "summary": p.get("summary") or max((g.get("summary") or "" for g in group), key=len),
            "tech": _clean_list([t for g in group for t in (g.get("tech") or [])]),
            "evidence": [e for g in group for e in g.get("evidence", [])],
            "people": [],
            "owner_titles": [t for t in (p.get("owner_titles") or []) if isinstance(t, str) and t.strip()][:5],
        }
        seen = set()
        for g in group:
            for person in g.get("people", []):
                if person["name"].lower() not in seen:
                    seen.add(person["name"].lower())
                    merged["people"].append(person)
        projects.append(merged)
    projects += cluster([c for i, c in enumerate(cands) if i not in used])  # anything the LLM left out
    return projects


def basis_of(init: dict, docs_by_key: dict) -> str:
    """'announced' if any non-job source describes the project, else 'hiring' (inferred from job posts only)."""
    types = {docs_by_key.get(e.get("doc"), {}).get("source_type") for e in init.get("evidence", [])}
    return "announced" if types & EVIDENCE_TYPES_ANNOUNCED else "hiring"


def describe_company(company: dict, docs: list[dict]) -> dict:
    """Industry, HQ country, website domain and a one-line summary, from the collected documents."""
    listing = "\n\n".join(f"{d.get('title', '')}\n{d['text'][:800]}" for d in docs[:8])
    prompt = f"""Company: {company['name']}
Documents:
{listing}

Return {{"industry": str, "hq_country": str, "domain": "example.com" or null, "summary": one sentence}}.
Use null for anything the documents do not support."""
    try:
        return llm.complete_json("You profile companies from public documents.", prompt, 400)
    except Exception:
        return {}


def extract(company: dict, docs: list[dict]) -> dict:
    """Returns {"initiatives": [...], "vendors": [...], "tech": [...], "people": [...]} across all batches."""
    out = {"initiatives": [], "vendors": [], "tech": [], "people": [], "locations": [], "job_locations": [], "projects": [],
           "errors": [], "batches": 0}
    for start in range(0, len(docs), 5):
        out["batches"] += 1
        batch = docs[start : start + 5]
        listing = "\n\n".join(
            f"[{d['key']}] ({d['source_type']}, {d.get('published_at') or 'undated'}) {d.get('title', '')}\n{d['text'][:3500]}"
            for d in batch
        )
        prompt = f"""Company: {company['name']}

Documents:
{listing}

Return {{
"initiatives": [{{
  "name": name of the underlying initiative (the work, not the hiring),
  "category": one of {list(CATEGORIES)},
  "stage": one of {STAGES},
  "summary": 1-2 sentences with concrete facts (scale, dates, tech, vendor status),
  "tech": [technologies/products mentioned],
  "evidence": [{{"doc": document key like "{batch[0]['key']}", "quote": exact short quote}}],
  "people": [{{"name": full name, "title": as written, "involvement": how they relate to this initiative,
              "reports_to": name or title of their manager ONLY if a document says so, else null}}]
}}],
"vendors": [{{"name": vendor or partner company, "relationship": one of ["selected","partner","incumbent","replacing","evaluating"],
             "area": what they provide, "deal_type": one of ["new","renewal","expansion","ended"] or null,
             "value": contract value as written (e.g. "$120 million") or null, "date": "YYYY-MM-DD" or "YYYY-MM" or null,
             "duration": e.g. "5 years" or null, "doc": document key, "quote": exact short quote}}],
"locations": [{{"city": city, "country": country, "type": one of {LOCATION_TYPES},
               "functions": [what is done there, e.g. "engineering","QA","data","operations"], "headcount": number if stated else null,
               "doc": document key, "quote": exact short quote}}],
"job_locations": [{{"city": city of ONE job post, "country": country, "function": e.g. "QA","engineering","data","product"}}],
"projects": [{{"name": short name of the work, "counterparty": the other company (required),
  "relationship": "external" if the counterparty is an independent company, "same_group" if it is {company['name']}'s parent, subsidiary or sister company,
  "direction": "client" if {company['name']} delivers the work for the counterparty, "partner" if the counterparty delivers it for {company['name']},
  "status": one of ["announced","won","in_progress","live","completed"], "summary": 1-2 sentences: what is being built or run, for whom, outcomes,
  "tech": [technologies], "value": contract value as written or null, "start": "YYYY-MM-DD" or "YYYY-MM" or null, "duration": e.g. "5 years" or null,
  "company_people": [{{"name": full name, "title": as written, "involvement": role on this project}}] ({company['name']} employees only),
  "counterparty_people": [{{"name": full name, "title": as written}}],
  "owner_titles": [2-4 job titles at {company['name']} who would run or own this engagement],
  "doc": document key, "quote": exact short quote}}],
"tech": [{{"name": technology, product or platform {company['name']} uses, "doc": document key}}],
"people": [{{"name": full name, "title": as written, "reports_to": manager name or title if stated, else null, "doc": document key}}]
}}
"locations" are {company['name']}'s own sites (offices, R&D/engineering centres, GCCs, plants), not its customers'.
"job_locations" has one entry per job post in the documents, so hiring by city can be counted.
"people" at the top level lists every {company['name']} employee named in the documents, including job-post hiring
managers ("reports to the Director of QA" -> reports_to "Director of QA").
Ignore generic marketing, other companies' initiatives, and anything older than {config.LOOKBACK_DAYS} days."""
        try:
            result = llm.complete_json(EXTRACT_SYSTEM, prompt, 5000)
        except Exception as exc:  # a bad batch should not sink the whole run, but say why
            out["errors"].append(config.redact(f"{type(exc).__name__}: {str(exc)[:300]}"))
            continue
        if not isinstance(result, dict):
            out["errors"].append(f"AI returned {type(result).__name__} instead of an object")
            continue
        for item in result.get("initiatives", []) or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            item["tech"] = _clean_list(item.get("tech"))
            item["evidence"] = [e for e in (item.get("evidence") or []) if isinstance(e, dict)]
            item["people"] = [p for p in (item.get("people") or []) if isinstance(p, dict) and p.get("name")]
            item["summary"] = item.get("summary") or ""
            if item.get("category") not in CATEGORIES:
                item["category"] = "other"
            if item.get("stage") not in STAGES:
                item["stage"] = "hinted"
            out["initiatives"].append(item)
        for key in ("vendors", "tech", "people", "locations"):
            out[key] += [x for x in (result.get(key) or []) if isinstance(x, dict) and (x.get("name") or x.get("city"))]
        out["job_locations"] += [x for x in (result.get("job_locations") or []) if isinstance(x, dict) and x.get("city")]
        out["projects"] += [x for x in (result.get("projects") or []) if isinstance(x, dict) and x.get("name")
                            and str(x.get("counterparty") or "").strip()]
    return out


# ---------------------------------------------------------------- cluster

_STOP = {"the", "a", "an", "of", "and", "to", "for", "new", "programme", "program", "initiative", "project", "rollout"}


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in _STOP}


def cluster(cands: list[dict]) -> list[dict]:
    """Merge candidates that describe the same initiative (same category + overlapping name)."""
    merged: list[dict] = []
    for c in cands:
        match = None
        for m in merged:
            if m["category"] != c["category"]:
                continue
            a, b = _tokens(m["name"]), _tokens(c["name"])
            if a and b and len(a & b) / min(len(a), len(b)) >= 0.5:
                match = m
                break
        if not match:
            merged.append({**c, "evidence": list(c.get("evidence", [])), "people": list(c.get("people", []))})
            continue
        # Keep the more specific name/summary, union everything else.
        if len(c.get("summary", "")) > len(match.get("summary", "")):
            match["summary"] = c["summary"]
        if STAGES.index(c.get("stage", "hinted")) > STAGES.index(match.get("stage", "hinted")):
            match["stage"] = c["stage"]
        match["tech"] = _clean_list(list(match.get("tech") or []) + list(c.get("tech") or []))
        match["evidence"] += c.get("evidence", [])
        known = {p["name"].lower() for p in match["people"]}
        match["people"] += [p for p in c.get("people", []) if p["name"].lower() not in known]
    return merged


# ---------------------------------------------------------------- people

_ALIASES = {
    "chief technology officer": "cto", "chief information officer": "cio", "chief executive officer": "ceo",
    "chief operating officer": "coo", "chief digital officer": "cdo", "chief information security officer": "ciso",
    "chief product officer": "cpo", "chief data officer": "chief data officer",
    "vice president": "vp", "quality assurance": "qa",
}


def _norm_title(t: str) -> set[str]:
    t = t.lower()
    for long, short in _ALIASES.items():
        t = t.replace(long, short)
    return {w for w in re.findall(r"[a-z0-9]+", t) if w not in {"of", "the", "and", "for"}}


def _title_matches(title: str, canonical: list[str]) -> bool:
    words = _norm_title(title)
    return any(_norm_title(c) <= words for c in canonical)


_CSUITE = {"cto", "cio", "ceo", "coo", "cdo", "cpo", "chief", "president", "founder"}


def in_function(title: str, cat_key: str) -> bool:
    """Does the person's title sit in the function that usually runs this kind of initiative?"""
    words = _norm_title(title)
    fw = set(category(cat_key).get("function_words", []))
    return not fw or bool(words & fw)


def is_buyer_persona(title: str, profile: dict) -> bool:
    """The seller's own buyer (e.g. Head of QA for a testing firm) is relevant to every initiative."""
    return _title_matches(title, profile.get("buyer_titles", []))


def classify(title: str, cat_key: str, involvement: str = "") -> tuple[str, float]:
    """Return (role, title_fit 0-1) for a person relative to an initiative category."""
    cat = category(cat_key)
    words = _norm_title(title)
    inv = involvement.lower()
    leads = any(k in inv for k in ("lead", "head", "owns", "run", "manager for", "hiring manager", "drive"))
    fits = in_function(title, cat_key)

    if "ciso" in words:
        return ("Owner", 0.9) if cat_key in ("cybersecurity", "compliance") else ("Influencer", 0.3)
    if _title_matches(title, cat["owner_titles"]) and fits:
        return "Owner", 1.0
    if words & _CSUITE or _title_matches(title, cat["sponsor_titles"]):
        return "Sponsor", 0.8 if _title_matches(title, cat["sponsor_titles"]) else 0.5
    if leads and words & {"head", "director", "vp"}:
        return "Owner", 0.9
    if _title_matches(title, cat["practitioner_titles"]) and fits:
        return "Practitioner", 0.8
    if words & {"head", "director", "vp"}:
        return "Influencer", 0.5
    if words & {"manager", "architect", "principal"}:
        return "Influencer", 0.4
    return "Practitioner", 0.3


def _relevant(title: str, init: dict, profile: dict) -> bool:
    """Keep a database person only if their title fits this initiative or is the seller's buyer persona."""
    role, fit = classify(title, init["category"])
    if role == "Sponsor":
        return _title_matches(title, category(init["category"])["sponsor_titles"])
    if _title_matches(title, init.get("owner_titles", [])):
        return True  # the AI's read of who owns this particular piece of work
    return (fit >= 0.8 and in_function(title, init["category"])) or is_buyer_persona(title, profile)


def domain_from_sources(name: str, docs: list[dict]) -> str | None:
    """The company's own site, guessed from the URLs of the pages read: the most common host whose name contains
    the company's first word (hdfcbank.com for 'HDFC Bank'). None when nothing fits."""
    import re as _re
    from collections import Counter
    first = _re.sub(r"[^a-z0-9]", "", (name.split() or [""])[0].lower())
    if len(first) < 3:
        return None
    hosts = Counter()
    for d in docs:
        host = _re.sub(r"^www\d?\.", "", (_re.match(r"https?://([^/:]+)", d.get("url") or "") or [None, ""])[1].lower())
        parts = host.split(".")
        if len(parts) < 2:
            continue
        root = ".".join(parts[-3:]) if parts[-2] in ("co", "com", "net", "org", "ac", "gov") and len(parts) >= 3 else ".".join(parts[-2:])
        if first in root.split(".")[0] and not any(x in root for x in ("linkedin", "naukri", "glassdoor", "indeed", "wikipedia")):
            hosts[root] += 1
    return hosts.most_common(1)[0][0] if hosts else None


def candidate_people(company: dict, init: dict, profile: dict, fb: dict | None = None,
                     named_pool: list[dict] | None = None) -> list[dict]:
    """People named in this initiative's evidence; leaders named elsewhere in the sources whose title fits it;
    and title-matched people from the people database."""
    people = [{**p, "full_name": p["name"], "source": "evidence"} for p in init.get("people", [])]
    named = {p["full_name"].lower() for p in people}
    for p in named_pool or []:  # e.g. the CIO quoted in an unrelated article, for a digital-banking rollout
        nm = (p.get("name") or p.get("full_name") or "").strip()
        if nm and nm.lower() not in named and p.get("title") and _relevant(p["title"], init, profile):
            people.append({**p, "full_name": nm, "source": "sources", "involvement": ""})
            named.add(nm.lower())
    cat = category(init["category"])
    titles = cat["owner_titles"] + cat["sponsor_titles"] + cat["practitioner_titles"] + profile.get("buyer_titles", [])
    titles = list(dict.fromkeys(init.get("owner_titles", []) + titles))

    found = apollo.search_people(company.get("domain") or "", titles, per_page=15)
    source = "apollo"
    for f in found:
        if f["full_name"].lower() in named:
            for p in people:  # fill in details for people already named in the evidence
                if p["full_name"].lower() == f["full_name"].lower():
                    p.update({k: v for k, v in f.items() if k not in ("full_name", "title") and v})
            continue
        if _relevant(f["title"], init, profile):
            people.append({**f, "source": source, "involvement": ""})
    if fb:  # never re-suggest someone your team rejected for this kind of initiative
        people = [p for p in people if fb["people"].get((p["full_name"].lower(), init["category"])) != "rejected"]
    return people


def score_person(p: dict, init: dict, recency_days: int | None, profile: dict, fb: dict | None = None) -> tuple[str, float, str]:
    role, title_fit = classify(p.get("title", ""), init["category"], p.get("involvement", ""))
    named = p["source"] == "evidence"
    in_sources = p["source"] == "sources"  # named at this company in the sources, just not about this initiative
    if role not in ("Owner", "Sponsor") and _title_matches(p.get("title", ""), init.get("owner_titles", [])):
        role, title_fit = "Owner", max(title_fit, 0.85)
    buyer = is_buyer_persona(p.get("title", ""), profile)
    if buyer and not named and role not in ("Owner", "Sponsor"):
        role, title_fit = "Influencer", 0.7
    score = 0.45 * named + 0.2 * in_sources + 0.30 * title_fit + (0.08 if buyer else 0)
    score += {"Owner": 0.15, "Sponsor": 0.12, "Influencer": 0.08, "Practitioner": 0.06}[role]
    if recency_days is not None:
        score += 0.10 * max(0.0, 1 - recency_days / config.LOOKBACK_DAYS)
    score += feedback.title_adjustment(init["category"], p.get("title", ""))  # learned across all companies
    label = category(init["category"])["label"]
    if fb and fb["people"].get((p["full_name"].lower(), init["category"])) == "confirmed":
        return role, 1.0, "Confirmed by your team as the right contact."
    if named:
        why = f"Named in the evidence: {p.get('involvement') or 'mentioned in a source'}."
    elif in_sources:
        why = f"Named in the sources as {p['title']}; that role usually owns or signs off {label} work like this."
    elif buyer and role == "Influencer":
        why = f"Your buyer persona ({p['title']}); usually decides on outside help for initiatives like this. Not named in sources."
    else:
        why = f"Title fits the usual {role.lower()} of {label} initiatives; not named in sources yet."
    return role, round(max(0.0, min(score, 0.99)), 2), why


# ---------------------------------------------------------------- openers


def opener(person: dict, init: dict, company: dict, profile: dict, fit_reason: str) -> str:
    first = person["full_name"].split()[0]
    offering = fit_reason.split(":")[0] if ":" in fit_reason else profile["offerings"][0]["name"]
    if llm.available():
        prompt = f"""Write a 2-sentence LinkedIn connection note (max 280 characters) from {profile['company']}
to {person['full_name']} ({person.get('title')}) at {company['name']}.
Hook: their initiative "{init['name']}": {init['summary']}
Relevant offering: {offering}. Specific, no flattery, no buzzwords, end with a light question."""
        try:
            return llm.complete("You write concise B2B outreach.", prompt, 300).strip()
        except Exception:
            pass
    return (
        f"Hi {first}, saw that {company['name']} is working on the {init['name']}. "
        f"We help teams at this stage with {offering[0].lower() + offering[1:]}. Open to comparing notes on what's worked elsewhere?"
    )


# ---------------------------------------------------------------- orchestrate


def _days_ago(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(date_str[:10]).replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - d).days)
    except ValueError:
        return None


def _save_people_pool(company_id: int, people: list[dict], key_to_id: dict, source: str) -> None:
    """Store people (named in sources, or the Apollo leadership pool) for the org chart."""
    with db.session() as s:
        for p in people:
            name = (p.get("full_name") or p.get("name") or "").strip()
            if not name or len(name) < 3:
                continue
            same = p.get("apollo_id") and s.execute(  # keep the name you revealed with Get email
                "SELECT full_name FROM person WHERE company_id=? AND apollo_id=?", (company_id, p["apollo_id"])).fetchone()
            if same:
                name = same["full_name"]
            s.execute(
                """INSERT INTO person(company_id, full_name, title, seniority, linkedin_url, apollo_id, source,
                   reports_to, reports_to_source, document_id) VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(company_id, full_name) DO UPDATE SET
                   title=COALESCE(excluded.title, title), seniority=COALESCE(excluded.seniority, seniority),
                   linkedin_url=COALESCE(excluded.linkedin_url, linkedin_url), apollo_id=COALESCE(excluded.apollo_id, apollo_id),
                   reports_to=CASE WHEN excluded.reports_to_source='evidence' THEN excluded.reports_to ELSE reports_to END,
                   reports_to_source=CASE WHEN excluded.reports_to_source='evidence' THEN 'evidence' ELSE reports_to_source END""",
                (company_id, name, p.get("title"), p.get("seniority"), p.get("linkedin_url"), p.get("apollo_id"), source,
                 p.get("reports_to"), "evidence" if p.get("reports_to") and source == "evidence" else None,
                 key_to_id.get(p.get("doc"))),
            )


def _save_vendors_and_tech(company_id: int, extracted: dict, key_to_id: dict, docs_by_key: dict, profile: dict, domain: str | None):
    competitors = [c.lower() for c in profile.get("competitors", []) if c.strip()]
    with db.session() as s:
        for v in extracted["vendors"]:
            name = v["name"].strip()
            if name.lower() in ("", "unknown"):
                continue
            is_comp = any(c in name.lower() or name.lower() in c for c in competitors)
            doc_date = norm_date((docs_by_key.get(v.get("doc")) or {}).get("published_at"))
            deal_date = _deal_date(v.get("date")) or doc_date
            s.execute(
                """INSERT OR IGNORE INTO vendor(company_id, name, relationship, area, quote, document_id, is_competitor,
                   deal_type, deal_value, deal_date, duration, scope) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (company_id, name, v.get("relationship"), v.get("area"), v.get("quote"), key_to_id.get(v.get("doc")), int(is_comp),
                 v.get("deal_type") if v.get("deal_type") in ("new", "renewal", "expansion", "ended") else None,
                 v.get("value"), deal_date, v.get("duration"), v.get("area")))
        for t in extracted["tech"]:
            doc = docs_by_key.get(t.get("doc"), {})
            s.execute("INSERT OR IGNORE INTO tech(company_id, name, category, source, document_id) VALUES (?,?,?,?,?)",
                      (company_id, t["name"].strip(), t.get("category"), doc.get("source_type", "news"), key_to_id.get(t.get("doc"))))
    # Website tech: free open-source fingerprinting; BuiltWith only if someone set a paid key.
    site_tech = webtech.lookup(domain or "") + (builtwith.lookup(domain or "") if builtwith.available() else [])
    with db.session() as s:
        for t in site_tech:
            s.execute("INSERT OR IGNORE INTO tech(company_id, name, category, source) VALUES (?,?,?,'website')",
                      (company_id, t["name"], t["category"]))


def _deal_date(value) -> str | None:
    if not value or not isinstance(value, str):
        return None
    if re.fullmatch(r"\d{4}-\d{2}", value.strip()):
        return value.strip()
    if re.fullmatch(r"\d{4}", value.strip()):
        return value.strip()
    return norm_date(value)


def _save_locations(company_id: int, extracted: dict, key_to_id: dict) -> None:
    def clean(x):
        return (x or "").strip().title() or None

    with db.session() as s:
        for loc in extracted["locations"]:
            city, country = clean(loc.get("city")), clean(loc.get("country"))
            if not (city or country):
                continue
            typ = loc.get("type") if loc.get("type") in LOCATION_TYPES else "other"
            hc = loc.get("headcount")
            try:
                hc = int(str(hc).replace(",", "").replace("+", "")) if hc not in (None, "") else None
            except ValueError:
                hc = None
            s.execute(
                """INSERT INTO location(company_id, city, country, type, functions, headcount, quote, document_id)
                   VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(company_id, city, country, type) DO UPDATE SET
                   headcount=COALESCE(excluded.headcount, headcount), functions=excluded.functions""",
                (company_id, city, country, typ, json.dumps(_clean_list(loc.get("functions"))), hc, loc.get("quote"),
                 key_to_id.get(loc.get("doc"))))
        counts: dict = {}
        for j in extracted["job_locations"]:
            city = clean(j.get("city"))
            if not city:
                continue
            c = counts.setdefault(city, {"country": clean(j.get("country")), "roles": 0, "functions": set()})
            c["roles"] += 1
            if j.get("function"):
                c["functions"].add(str(j["function"]).strip().lower())
        for city, c in counts.items():
            s.execute("INSERT OR REPLACE INTO job_location(company_id, city, country, roles, functions) VALUES (?,?,?,?,?)",
                      (company_id, city, c["country"], c["roles"], json.dumps(sorted(c["functions"]))))


def run(run_id: int, company_id: int, force: bool = False) -> None:
    """Research one account, inside that account's workspace."""
    with tenancy.use(tenancy.of_company(company_id) or 1):
        _run(run_id, company_id, force)


def _run(run_id: int, company_id: int, force: bool = False) -> None:
    log = lambda m: db.append_log(run_id, m)  # noqa: E731
    with db.session() as s:
        s.execute("UPDATE run SET status='running' WHERE id=?", (run_id,))
        company = dict(s.execute("SELECT * FROM company WHERE id=?", (company_id,)).fetchone())
    try:
        if not config.configured():
            raise RuntimeError("Add TAVILY_API_KEY plus ANTHROPIC_API_KEY or OPENAI_API_KEY to .env, then restart the app.")
        profile = profiles.load()
        fb = feedback.for_company(company_id)
        before = alerts.snapshot(company_id)

        if not force and sources_fresh(company) and stored_documents(company_id):
            log(f"Collecting public signals for {company['name']}: re-using sources fetched in the last {config.SOURCE_CACHE_HOURS:g} hours")
        else:
            log(f"Collecting public signals for {company['name']}: news, job boards, careers pages, filings, blogs")
            fetched = collect(company)
            save_documents(company_id, fetched)
            log(f"Read {len(fetched)} full pages")
        docs = stored_documents(company_id)
        if not docs:
            raise RuntimeError(f"No public documents found for {company['name']}. Check the spelling or add its website domain.")
        key_to_id = {d["key"]: d["id"] for d in docs}
        docs_by_key = {d["key"]: d for d in docs}

        if not company.get("industry") or force:
            info = describe_company(company, docs)
            with db.session() as s:
                s.execute(
                    """UPDATE company SET domain=COALESCE(domain, ?), industry=COALESCE(?, industry),
                       hq_country=COALESCE(?, hq_country), summary=COALESCE(?, summary) WHERE id=?""",
                    (info.get("domain"), info.get("industry"), info.get("hq_country"), info.get("summary"), company_id),
                )
                company = dict(s.execute("SELECT * FROM company WHERE id=?", (company_id,)).fetchone())
        if not company.get("domain"):
            guess = domain_from_sources(company["name"], docs)
            if guess:
                with db.session() as s:
                    s.execute("UPDATE company SET domain=? WHERE id=? AND domain IS NULL", (guess, company_id))
                company["domain"] = guess
                log(f"Website taken from the sources: {guess}")
        if not company.get("domain"):
            log("No website domain known, so careers pages and the people search are skipped. Add it and research again.")
        elif not apollo.available():
            log("APOLLO_API_KEY isn't set, so only people named in the sources are used")
        dates = {d["key"]: d.get("published_at") for d in docs}
        log(f"Analysing {len(docs)} sources: " + ", ".join(sorted({d['source_type'] for d in docs})))

        log("Extracting initiatives, vendors, tech and reporting lines from the documents")
        extracted = extract(company, docs)
        if extracted["errors"]:
            log(f"AI extraction failed on {len(extracted['errors'])} of {extracted['batches']} batches. "
                f"First error: {extracted['errors'][0]}")
            if len(extracted["errors"]) == extracted["batches"]:
                raise RuntimeError("The AI step failed on every batch, so no initiatives could be extracted. "
                                   f"Error: {extracted['errors'][0]}. Run `python -m backend.doctor` to check your keys and model.")
        inits = consolidate(company, extracted["initiatives"])
        dismissed = [i for i in inits if feedback.initiative_verdict(fb, i["name"]) == "dismissed"]
        inits = [i for i in inits if i not in dismissed]
        log(f"{len(extracted['initiatives'])} candidate initiatives merged into {len(inits)}"
            + (f" ({len(dismissed)} you dismissed earlier skipped)" if dismissed else ""))

        kept = db.clear_company_results(company_id)
        kept_match, unmatched = {}, list(kept)
        for n, init in enumerate(inits):
            for k in unmatched:
                if feedback.same_initiative(k["name"], init["name"]):
                    kept_match[n] = k
                    unmatched.remove(k)
                    break
        if kept:
            log(f"Keeping {len(kept)} initiative(s) you've worked on (emails fetched or contacts reviewed); "
                f"{len(kept_match)} found again and updated")
        log(f"Judging fit against what {profile.get('company', 'you')} sells")
        fits = profiles.fit_many(profile, company, inits)
        if unmatched:  # still on the list; re-judge them against the current profile too
            for k in unmatched:
                k["tech"] = json.loads(k.get("tech") or "[]")
            with db.session() as s:
                for k, (sc, why) in zip(unmatched, profiles.fit_many(profile, company, unmatched)):
                    s.execute("UPDATE initiative SET fit_score=?, fit_reason=? WHERE id=?", (sc, why, k["id"]))
        _save_vendors_and_tech(company_id, extracted, key_to_id, docs_by_key, profile, company.get("domain"))
        _save_locations(company_id, extracted, key_to_id)
        named_people = extracted["people"] + [p for i in inits for p in i.get("people", [])]
        _save_people_pool(company_id, named_people, key_to_id, "evidence")
        if company.get("domain"):
            apollo.last_error = None
            pool = apollo.leadership(company["domain"])
            _save_people_pool(company_id, pool, key_to_id, "apollo")
            if apollo.last_error:
                log(f"People database search failed: {apollo.last_error}. Only people named in the sources are used.")
            elif apollo.available() and not pool:
                log(f"The people database has no leaders listed for {company['domain']}")

        for n, init in enumerate(inits):
            fit_score, fit_reason = fits[n]
            ev = [e for e in init.get("evidence", []) if e.get("doc") in key_to_id]
            ev_dates = sorted(d for d in (norm_date(dates.get(e["doc"])) for e in ev) if d)
            ages = [a for a in (_days_ago(x) for x in ev_dates) if a is not None]
            recency = min(ages, default=None)
            basis = basis_of({"evidence": ev}, docs_by_key)
            confidence = min(1.0, 0.35 + 0.15 * len({e["doc"] for e in ev}) + (0.1 if init["stage"] in STAGES[2:] else 0))
            if basis == "hiring":
                confidence = min(confidence, 0.5)  # job posts alone only hint at the project
            verdict = feedback.initiative_verdict(fb, init["name"])
            with db.session() as s:
                k = kept_match.get(n)
                if k:  # same work as one you've already worked on: refresh it, keep its name, verdict and contacts
                    s.execute(
                        """UPDATE initiative SET category=?, stage=?, summary=?, tech=?, first_seen=MIN(COALESCE(first_seen, ?), COALESCE(?, first_seen)),
                           last_seen=MAX(COALESCE(last_seen, ''), COALESCE(?, '')), confidence=MAX(COALESCE(confidence, 0), ?),
                           fit_score=?, fit_reason=?, basis=CASE WHEN basis='announced' THEN basis ELSE ? END WHERE id=?""",
                        (init["category"], init["stage"], init.get("summary", ""), json.dumps(init.get("tech", [])),
                         min(ev_dates, default=None), min(ev_dates, default=None), max(ev_dates, default=None),
                         round(confidence, 2), fit_score, fit_reason, basis, k["id"]),
                    )
                    iid = k["id"]
                else:
                    cur = s.execute(
                        """INSERT INTO initiative(company_id, name, category, stage, summary, tech, first_seen, last_seen,
                           confidence, fit_score, fit_reason, feedback, basis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (company_id, init["name"], init["category"], init["stage"], init.get("summary", ""),
                         json.dumps(init.get("tech", [])), min(ev_dates, default=None), max(ev_dates, default=None),
                         round(confidence, 2), fit_score, fit_reason, verdict, basis),
                    )
                    iid = cur.lastrowid
                for e in ev:
                    s.execute(
                        "INSERT OR IGNORE INTO initiative_evidence(initiative_id, document_id, quote) VALUES (?,?,?)",
                        (iid, key_to_id[e["doc"]], e.get("quote", "")),
                    )

            people = candidate_people(company, init, profile, fb, named_people)
            ranked = []
            for p in people:
                role, score, why = score_person(p, init, recency, profile, fb)
                ranked.append((score, role, why, p))
            ranked.sort(key=lambda x: -x[0])
            with db.session() as s:
                for score, role, why, p in ranked[: config.MAX_CONTACTS_PER_INITIATIVE]:
                    same = p.get("apollo_id") and s.execute(  # Apollo masks surnames; match people you've revealed by id
                        "SELECT id, full_name FROM person WHERE company_id=? AND apollo_id=?", (company_id, p["apollo_id"])).fetchone()
                    if same:
                        p = {**p, "full_name": same["full_name"]}
                    s.execute(
                        """INSERT INTO person(company_id, full_name, title, seniority, linkedin_url, apollo_id, source)
                           VALUES (?,?,?,?,?,?,?) ON CONFLICT(company_id, full_name) DO UPDATE SET
                           title=COALESCE(excluded.title, title), apollo_id=COALESCE(excluded.apollo_id, apollo_id),
                           linkedin_url=COALESCE(excluded.linkedin_url, linkedin_url)""",
                        (company_id, p["full_name"], p.get("title"), p.get("seniority"), p.get("linkedin_url"),
                         p.get("apollo_id"), p["source"]),
                    )
                    pid = s.execute(
                        "SELECT id FROM person WHERE company_id=? AND full_name=?", (company_id, p["full_name"])
                    ).fetchone()["id"]
                    msg = opener(p, init, company, profile, fit_reason)
                    pv = fb["people"].get((p["full_name"].lower(), init["category"]))
                    s.execute(
                        """INSERT INTO initiative_contact(initiative_id, person_id, role, score, rationale, opener,
                           source, feedback) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(initiative_id, person_id) DO UPDATE SET
                           role=excluded.role, score=MAX(score, excluded.score), rationale=excluded.rationale,
                           opener=COALESCE(opener, excluded.opener), source=excluded.source,
                           feedback=COALESCE(feedback, excluded.feedback)""",
                        (iid, pid, role, score, why, msg, p["source"], pv),
                    )
            log(f"  {init['name']}: {min(len(ranked), config.MAX_CONTACTS_PER_INITIATIVE)} contacts, fit {fit_score}")

        try:
            n_proj, n_new = projects.save(company, extracted["projects"], key_to_id, docs_by_key, profile)
            log(f"{n_proj} client/partner project(s) found" + (f", {n_new} new" if n_new else ""))
        except Exception as exc:  # projects are additive; never fail the whole run over them
            log(f"Projects step failed: {exc}")

        with db.session() as s:
            s.execute("UPDATE run SET status='done', finished_at=CURRENT_TIMESTAMP WHERE id=?", (run_id,))
            s.execute("UPDATE company SET last_researched_at=? WHERE id=?", (_now(), company_id))
        new_alerts = alerts.diff_and_store(company_id, before)
        if new_alerts:
            log(f"{len(new_alerts)} change(s) since the last check: " + "; ".join(a["title"] for a in new_alerts))
        log("Done")
    except Exception as exc:  # surface any failure in the UI
        with db.session() as s:
            s.execute(
                "UPDATE run SET status='failed', error=?, finished_at=CURRENT_TIMESTAMP WHERE id=?", (config.redact(str(exc)), run_id)
            )
        log(f"Failed: {exc}")
