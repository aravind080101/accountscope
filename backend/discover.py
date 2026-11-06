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
publisher, a vendor quoted in passing, or an analyst firm. Skip results where no specific company is named.
When the user names regions, they want companies whose activity is IN those regions. A company qualifies only if
the signal itself happens there (the hiring, launch, office, appointment is located there) or, when the source
gives no location for the signal, the company is headquartered there. A global company's news from another
country does not qualify. If you can't tell where it happens, leave it out."""


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
    region = locations.describe(places)
    allowed = locations.allowed_countries(places)
    results = []
    if not places:
        results += tavily.raw_search(base, topic="news", days=days, max_results=20)
        results += tavily.raw_search(base, topic="general", days=None, max_results=10)
    else:
        # One search per place so a small market isn't drowned out by a big one; news pinned to the place
        # by name, web search also boosted to that country.
        picked = places[:5]
        per = max(6, 20 // len(picked))
        for place in picked:
            q = f"{base} in {place}"
            results += tavily.raw_search(q, topic="news", days=days, max_results=per)
            results += tavily.raw_search(q, topic="general", days=None, max_results=max(4, per // 2),
                                         country=locations.tavily_country(place))
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
    where = (f"""Regions: {region}
Only companies whose signal happens in these regions (see the rules). For each, say where it happens.""" if places else "")
    prompt = f"""Signal we are looking for: {signal_name}
{where}

Search results:
{listing}

Return {{"companies": [{{"company": official company name, "domain": website domain or null,
"country": the company's headquarters country or null,
"location": where this signal happens, "City, Country" (or just the country) as stated in the source, or null,
"signal_country": the country of that location in plain English (e.g. India, United Arab Emirates, United States), or null,
"in_region": true only if the signal happens in the regions above (or no regions were given),
"signal": one sentence on what this company is doing, with a concrete fact,
"source": result number}}]}}. One entry per company; most relevant first; at most 25."""
    out = llm.complete_json(RADAR_SYSTEM, prompt, 3500).get("companies", [])
    if places:
        kept = []
        for c in out:
            if c.get("in_region") is False:
                continue
            if allowed:
                # where the signal happens, else the head office: must be one of the chosen countries
                where_c = locations.country_name(c.get("signal_country")) or locations.country_name(
                    (c.get("location") or "").split(",")[-1]) or locations.country_name(c.get("country"))
                if not where_c or where_c not in allowed:
                    continue
            kept.append(c)
        out = kept
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
            "location": c.get("location"),
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
