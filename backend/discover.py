"""Discover: find companies to research without typing names.

1. Signal radar  - search recent news/job posts for a buying signal ("hiring testers",
                   "core banking migration"...) and let the LLM list the companies showing it.
2. Browse        - Apollo company search by keywords, country and size.
"""
from . import tenancy, config, db, llm, locations
from .providers import apollo, tavily

PRESETS = [
    {"id": "qa_hiring", "label": "Hiring testers",
     "query": 'company hiring SDET OR "test automation engineers" OR "QA engineers" team expansion'},
    {"id": "app_launch", "label": "Launching an app or platform",
     "query": "company launches new mobile app OR digital platform OR relaunches app"},
    {"id": "migration", "label": "Platform migration",
     "query": '"core banking" OR "cloud migration" OR "S/4HANA" OR "legacy modernisation" programme company announces'},
    {"id": "genai", "label": "Rolling out GenAI",
     "query": "company rolls out generative AI assistant OR AI copilot OR LLM chatbot for customers"},
    {"id": "new_leader", "label": "New tech leader",
     "query": 'company appoints "chief technology officer" OR "chief information officer" OR "chief digital officer"'},
    {"id": "funding", "label": "Raised funding",
     "query": "startup raises Series B OR Series C funding to scale technology and engineering"},
    {"id": "gcc", "label": "Opening a tech centre",
     "query": "company opens global capability centre OR new technology centre OR engineering hub"},
    {"id": "outage", "label": "Outage or app complaints",
     "query": "app outage OR users complain app crashes OR payment failures company apologises"},
]

RADAR_SYSTEM = """You turn news and job-post search results into a list of companies showing a buying signal.
List only the company the signal is ABOUT (the one hiring, launching, migrating, appointing), never the
publisher, a vendor quoted in passing, or an analyst firm. Skip results where no specific company is named."""


def _existing_accounts() -> dict[str, int]:
    with db.session() as s:
        return {r["name"].lower(): r["id"] for r in s.execute("SELECT id, name FROM company WHERE workspace_id=?",
                                                               (tenancy.current(),))}


def signal_radar(preset: str | None, query: str | None, region=None, days: int = 30) -> list[dict]:
    p = next((x for x in PRESETS if x["id"] == preset), None)
    base = (query or "").strip() or (p["query"] if p else "")
    if not base:
        raise ValueError("Pick a signal or type what to look for")
    places = locations.clean(region)
    region = ", ".join(places)
    results = []
    if not places:
        results += tavily.raw_search(base, topic="news", days=days, max_results=20)
        results += tavily.raw_search(base, topic="general", days=None, max_results=10)
    else:
        # One search per place so a small market isn't drowned out by a big one.
        picked = places[:5]
        per = max(6, 20 // len(picked))
        for place in picked:
            q = f"{base} {place}"
            results += tavily.raw_search(q, topic="news", days=days, max_results=per)
            results += tavily.raw_search(q, topic="general", days=None, max_results=max(4, per // 2))
    seen, docs = set(), []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            docs.append(r)
    if not docs:
        return []

    listing = "\n\n".join(
        f"[{i}] {d['title']} ({d.get('published_at') or 'undated'})\n{d['url']}\n{d['text'][:700]}"
        for i, d in enumerate(docs)
    )
    signal_name = p["label"] if p else base
    prompt = f"""Signal we are looking for: {signal_name}
{f'Only include companies with operations in: {region}' if region else ''}

Search results:
{listing}

Return {{"companies": [{{"company": official company name, "domain": website domain or null,
"country": country or null, "signal": one sentence on what this company is doing, with a concrete fact,
"source": result number}}]}}. One entry per company; most relevant first; at most 25."""
    out = llm.complete_json(RADAR_SYSTEM, prompt, 3000).get("companies", [])
    existing = _existing_accounts()
    rows, names = [], set()
    for c in out:
        name = (c.get("company") or "").strip()
        if not name or name.lower() in names:
            continue
        names.add(name.lower())
        src = docs[c["source"]] if isinstance(c.get("source"), int) and 0 <= c["source"] < len(docs) else {}
        rows.append({
            "name": name,
            "domain": c.get("domain"),
            "country": c.get("country"),
            "signal": c.get("signal", ""),
            "source_url": src.get("url"),
            "source_title": src.get("title"),
            "published_at": src.get("published_at"),
            "account_id": existing.get(name.lower()),
        })
    return rows


SIZES = {
    "1-50": "1,50", "51-200": "51,200", "201-1000": "201,1000",
    "1001-5000": "1001,5000", "5001-10000": "5001,10000", "10000+": "10001,1000000",
}


def browse(keywords: str | None, location=None, size: str | None = None, page: int = 1) -> dict:
    if not apollo.available():
        raise ValueError("Browsing companies needs APOLLO_API_KEY in .env")
    tags = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    data = apollo.search_companies(
        keywords=tags,
        locations=locations.for_apollo(location),
        sizes=[SIZES[size]] if size in SIZES else [],
        page=page,
    )
    existing = _existing_accounts()
    for c in data["companies"]:
        c["account_id"] = existing.get(c["name"].lower())
    return data


def presets() -> list[dict]:
    return [{"id": p["id"], "label": p["label"]} for p in PRESETS]


def location_catalog() -> list[dict]:
    return locations.catalog()


def available() -> dict:
    return {"radar": config.configured(), "browse": apollo.available()}
