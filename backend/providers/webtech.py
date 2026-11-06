"""Free website tech-stack detection (BuiltWith-style) using open-source Wappalyzer fingerprints.

Loads the company's homepage once, then matches its HTML, script URLs, meta tags and response
headers against the fingerprints bundled with `wappalyzer-python3` (GPLv3). No API key, no credits.
Results are cached for 30 days.
"""
import warnings

import httpx

from .. import cache

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
_engine = None


def _wappalyzer():
    global _engine
    if _engine is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from Wappalyzer import Wappalyzer  # bundled fingerprints; do NOT pass update=True

            _engine = Wappalyzer.latest()
    return _engine


def fetch(domain: str) -> tuple[str, str, dict] | None:
    """Return (final_url, html, headers) for the company's homepage, trying https://domain then www."""
    for url in (f"https://{domain}", f"https://www.{domain}"):
        try:
            r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, follow_redirects=True, timeout=20)
        except httpx.HTTPError:
            continue
        if r.status_code < 400 and "html" in r.headers.get("content-type", "html"):
            return str(r.url), r.text[:3_000_000], dict(r.headers)
    return None


def analyze(url: str, html: str, headers: dict) -> list[dict]:
    from Wappalyzer import WebPage

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        found = _wappalyzer().analyze_with_versions_and_categories(WebPage(url, html=html, headers=headers))
    out = []
    for name, info in sorted(found.items()):
        cats = info.get("categories") or []
        version = (info.get("versions") or [None])[0]
        out.append({"name": f"{name} {version}" if version else name, "category": ", ".join(cats)})
    return out


def lookup(domain: str) -> list[dict]:
    if not domain:
        return []
    key = f"webtech:{domain}"
    hit = cache.get(key, 24 * 30)
    if hit is not None:
        return hit
    page = fetch(domain)
    if not page:
        return []
    try:
        techs = analyze(*page)
    except Exception:
        return []
    cache.put(key, techs)
    return techs
