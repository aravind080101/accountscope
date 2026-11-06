"""Check every external service the app depends on.   Run:  python -m backend.doctor"""
import json
import sys

import httpx

from . import config, llm


def check(name, fn):
    try:
        msg = fn()
        print(f"  OK    {name}: {msg}")
        return True
    except Exception as exc:
        print(f"  FAIL  {name}: {type(exc).__name__}: {str(exc)[:400]}")
        return False


def check_llm():
    provider = config.llm_provider()
    if not provider:
        raise RuntimeError("no ANTHROPIC_API_KEY or OPENAI_API_KEY in .env")
    model = config.OPENAI_MODEL if provider == "openai" else config.LLM_MODEL
    out = llm.complete_json("You are a test.", 'Return {"ok": true, "projects": ["test"]} as JSON.', 200)
    if not isinstance(out, dict) or not out.get("ok"):
        raise RuntimeError(f"unexpected reply from {model}: {json.dumps(out)[:200]}")
    return f"{provider} / {model} returns valid JSON"


def check_tavily():
    if not config.TAVILY_API_KEY:
        raise RuntimeError("no TAVILY_API_KEY in .env")
    r = httpx.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"},
                   json={"query": "Infosys announces new platform", "max_results": 3, "include_raw_content": True}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    res = r.json().get("results", [])
    full = sum(1 for x in res if x.get("raw_content"))
    return f"{len(res)} results, {full} with full page text"


def check_apollo():
    if not config.APOLLO_API_KEY:
        return "not set (optional): contacts will only be people named in sources"
    r = httpx.post("https://api.apollo.io/api/v1/mixed_people/api_search",
                   headers={"X-Api-Key": config.APOLLO_API_KEY, "Content-Type": "application/json"},
                   json={"q_organization_domains_list": ["infosys.com"], "person_titles": ["CTO"], "per_page": 1}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return f"people search works ({len(r.json().get('people', []))} result)"


if __name__ == "__main__":
    print("AccountScope doctor\n")
    ok = all([check("AI model", check_llm), check("Tavily search", check_tavily), check("Apollo", check_apollo)])
    print("\nAll good." if ok else "\nFix the FAIL lines above (usually a key, plan limit or model name in .env), then restart the app.")
    sys.exit(0 if ok else 1)
