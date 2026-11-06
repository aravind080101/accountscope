"""Optional website tech-stack lookup via BuiltWith (https://api.builtwith.com).
Only used when BUILTWITH_API_KEY is set; results are cached for 30 days."""
import httpx

from .. import cache, config


def available() -> bool:
    return bool(config.BUILTWITH_API_KEY)


def lookup(domain: str) -> list[dict]:
    if not (available() and domain):
        return []
    key = f"builtwith:{domain}"
    hit = cache.get(key, 24 * 30)
    if hit is not None:
        return hit
    try:
        resp = httpx.get(config.BUILTWITH_URL, params={"KEY": config.BUILTWITH_API_KEY, "LOOKUP": domain}, timeout=40)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    techs, seen = [], set()
    for res in data.get("Results", []) or []:
        for path in (res.get("Result") or {}).get("Paths", []) or []:
            for t in path.get("Technologies", []) or []:
                name = t.get("Name")
                if name and name.lower() not in seen:
                    seen.add(name.lower())
                    techs.append({"name": name, "category": t.get("Tag") or ""})
    techs = techs[:80]
    cache.put(key, techs)
    return techs
