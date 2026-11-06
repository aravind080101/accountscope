"""People search and enrichment via Apollo (https://docs.apollo.io).

search_people() uses the People API Search endpoint, which returns names and titles
without spending credits. enrich() spends a credit to reveal email/phone, so the app
calls it only when a user clicks "Enrich" on a contact.
"""
import httpx

from .. import config

BASE = "https://api.apollo.io/api/v1"


def _headers() -> dict:
    return {"X-Api-Key": config.APOLLO_API_KEY, "Content-Type": "application/json"}


def available() -> bool:
    return bool(config.APOLLO_API_KEY)


LEADERSHIP_TITLES = [
    "CEO", "CTO", "CIO", "COO", "Chief Digital Officer", "Chief Product Officer", "Chief Data Officer", "CISO",
    "VP Engineering", "VP Technology", "VP Product", "Head of Engineering", "Head of QA", "Head of Quality",
    "Head of Digital", "Head of Data", "Head of Platform", "Director Engineering", "Director Quality Engineering",
    "Engineering Manager", "QA Manager",
]


def search_people(domain: str, titles: list[str], per_page: int = 10) -> list[dict]:
    """People search by title at one company. Cached, since repeat lookups return the same people."""
    if not (available() and domain):
        return []
    from .. import cache  # local import: cache needs the DB, which the app sets up first

    key = f"apollo:people:{domain}:{'|'.join(sorted(t.lower() for t in titles))}:{per_page}"
    hit = cache.get(key, config.PEOPLE_CACHE_DAYS * 24)
    if hit is not None:
        return hit
    people = _search_people(domain, titles, per_page)
    if people:
        cache.put(key, people)
    return people


def leadership(domain: str) -> list[dict]:
    """A broader pool of leaders across functions, used to draw the org chart."""
    return search_people(domain, LEADERSHIP_TITLES, per_page=40)


def _search_people(domain: str, titles: list[str], per_page: int) -> list[dict]:
    body = {
        "q_organization_domains_list": [domain],
        "person_titles": titles,
        "person_seniorities": ["c_suite", "vp", "head", "director", "manager"],
        "per_page": per_page,
        "page": 1,
    }
    try:
        resp = httpx.post(f"{BASE}/mixed_people/api_search", json=body, headers=_headers(), timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    people = []
    for p in resp.json().get("people", []):
        last = p.get("last_name") or p.get("last_name_obfuscated") or ""
        name = f"{p.get('first_name', '')} {last}".strip()
        if not name:
            continue
        people.append(
            {
                "full_name": name,
                "title": p.get("title") or "",
                "seniority": p.get("seniority") or "",
                "linkedin_url": p.get("linkedin_url"),
                "apollo_id": p.get("id"),
            }
        )
    return people


def search_companies(keywords: list[str], locations: list[str], sizes: list[str], page: int = 1,
                     per_page: int = 25) -> dict:
    """Organization search. Note: depending on your Apollo plan this may use credits."""
    body: dict = {"page": page, "per_page": per_page}
    if keywords:
        body["q_organization_keyword_tags"] = keywords
    if locations:
        body["organization_locations"] = locations
    if sizes:
        body["organization_num_employees_ranges"] = sizes
    resp = httpx.post(f"{BASE}/mixed_companies/search", json=body, headers=_headers(), timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Apollo company search failed ({resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    orgs = (data.get("organizations") or []) + (data.get("accounts") or [])
    seen, companies = set(), []
    for o in orgs:
        name = o.get("name")
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        companies.append({
            "name": name,
            "domain": o.get("primary_domain") or (o.get("website_url") or "").replace("http://", "").replace("https://", "").strip("/") or None,
            "industry": o.get("industry"),
            "employees": o.get("estimated_num_employees"),
            "country": o.get("country"),
            "city": o.get("city"),
            "linkedin_url": o.get("linkedin_url"),
        })
    pag = data.get("pagination") or {}
    return {"companies": companies, "page": pag.get("page", page), "total_pages": pag.get("total_pages"),
            "total": pag.get("total_entries")}


def enrich(apollo_id: str | None, full_name: str, domain: str | None) -> dict:
    """Reveal email (and phone when available). Costs Apollo credits."""
    if not available():
        return {}
    body: dict = {"reveal_personal_emails": False}
    if apollo_id:
        body["id"] = apollo_id
    else:
        body.update(name=full_name, domain=domain)
    resp = httpx.post(f"{BASE}/people/match", json=body, headers=_headers(), timeout=30)
    resp.raise_for_status()
    p = resp.json().get("person") or {}
    phones = p.get("phone_numbers") or []
    return {
        "email": p.get("email"),
        "phone": phones[0].get("sanitized_number") if phones else None,
        "linkedin_url": p.get("linkedin_url"),
        "title": p.get("title"),
        "full_name": p.get("name"),
    }
