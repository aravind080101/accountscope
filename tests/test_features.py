"""Tests for full-page sources, org chart, alerts, tech & vendors, feedback and caching.
External services are replaced by stand-in responses."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import alerts, cache, config, db, orgchart, pipeline
from backend.app import app
from backend.providers import apollo, tavily

client = TestClient(app, headers={"X-Requested-With": "accountscope"})

DOCS_V1 = [
    {"source_type": "jobs", "url": "https://naukri.test/j1", "title": "SDET - Lending Platform", "published_at": "2026-10-20",
     "text": "Zen Finance is hiring SDETs for the new lending platform. This role reports to the Head of QA. " * 3},
    {"source_type": "vendor", "url": "https://news.test/v1", "title": "Zen picks CoreSoft", "published_at": "2026-09-10",
     "text": "Zen Finance selected CoreSoft for its lending platform, said CTO Ravi Iyer. TestCo handles regression testing. " * 3},
]
DOCS_V2 = DOCS_V1 + [
    {"source_type": "news", "url": "https://news.test/n2", "title": "Zen launches GenAI advisor", "published_at": "2026-10-30",
     "text": "Zen Finance launched a GenAI advisor led by Asha Rao, Head of AI. " * 3},
] + [{"source_type": "jobs", "url": f"https://naukri.test/x{i}", "title": f"QA role {i}", "published_at": "2026-10-29",
      "text": "Zen Finance QA automation engineer opening with Playwright. " * 4} for i in range(6)]

EXTRACT_V1 = {
    "initiatives": [{"name": "Lending platform rebuild", "category": "app_modernization", "stage": "announced",
                     "summary": "New lending platform on CoreSoft.", "tech": ["CoreSoft", "Playwright"],
                     "evidence": [{"doc": "KEY0", "quote": "hiring SDETs"}],
                     "people": [{"name": "Ravi Iyer", "title": "CTO", "involvement": "announced the platform", "reports_to": None}]}],
    "vendors": [{"name": "CoreSoft", "relationship": "selected", "area": "lending platform", "doc": "KEY1", "quote": "selected CoreSoft"},
                {"name": "TestCo", "relationship": "incumbent", "area": "regression testing", "doc": "KEY1", "quote": "TestCo handles"}],
    "tech": [{"name": "Playwright", "doc": "KEY0"}, {"name": "CoreSoft", "doc": "KEY1"}],
    "people": [{"name": "Meena S", "title": "Head of QA", "reports_to": "Ravi Iyer", "doc": "KEY0"}],
}

PEOPLE = [
    {"full_name": "Ravi Iyer", "title": "Chief Technology Officer", "seniority": "c_suite", "linkedin_url": None, "apollo_id": "1"},
    {"full_name": "Meena S", "title": "Head of QA", "seniority": "head", "linkedin_url": None, "apollo_id": "2"},
    {"full_name": "Arun K", "title": "QA Manager", "seniority": "manager", "linkedin_url": None, "apollo_id": "3"},
    {"full_name": "Dev P", "title": "SDET Lead", "seniority": "senior", "linkedin_url": None, "apollo_id": "4"},
    {"full_name": "Kiran M", "title": "CEO", "seniority": "c_suite", "linkedin_url": None, "apollo_id": "5"},
    {"full_name": "Sam T", "title": "Director Engineering", "seniority": "director", "linkedin_url": None, "apollo_id": "6"},
]

calls = {"tavily": 0}


@pytest.fixture
def env(monkeypatch):
    return install_fakes(monkeypatch)


def install_fakes(monkeypatch):
    """Replace Tavily, the LLM and Apollo with stand-ins. Returns mutable state for the test to change."""
    calls["tavily"] = 0
    state = {"docs": DOCS_V1, "extract": EXTRACT_V1}
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    monkeypatch.setattr(config, "APOLLO_API_KEY", "x")
    monkeypatch.setattr(config, "COMPETITORS_TEST", True, raising=False)

    def fake_search(name, domain=None):
        calls["tavily"] += 1
        return [dict(d) for d in state["docs"]]

    def fake_json(system, prompt, *a, **k):
        if "profile companies" in system:
            return {"industry": "Lending", "hq_country": "India", "domain": "zen.test", "summary": "A lender."}
        # map placeholder doc keys to the real keys used in this prompt
        import re
        keys = re.findall(r"\[(doc\d+)\]", prompt)
        url_order = [d["url"] for d in state["docs"]]
        with db.session() as s:
            rows = {r["url"]: f"doc{r['id']}" for r in s.execute("SELECT id, url FROM document")}
        key_for = {f"KEY{i}": rows.get(u) for i, u in enumerate(url_order)}
        import json as _j
        text = _j.dumps(state["extract"])
        for k, v in key_for.items():
            if v:
                text = text.replace(f'"{k}"', f'"{v}"')
        out = _j.loads(text)
        if keys and not any(k in keys for k in key_for.values()):
            return {"initiatives": [], "vendors": [], "tech": [], "people": []}
        return out

    monkeypatch.setattr(tavily, "search", fake_search)
    monkeypatch.setattr(pipeline.llm, "complete_json", fake_json)
    monkeypatch.setattr(pipeline.llm, "complete", lambda *a, **k: "Hi, short note.")
    monkeypatch.setattr(pipeline.llm, "available", lambda: True)
    monkeypatch.setattr(apollo, "_search_people", lambda domain, titles, per_page: [dict(p) for p in PEOPLE])
    from backend.providers import webtech
    monkeypatch.setattr(webtech, "fetch", lambda domain: None)   # no real website calls in tests
    return state


def _research(name):
    r = client.post("/api/accounts", json={"name": name, "domain": "zen.test"}).json()
    return r["company_id"]


def test_full_flow_org_vendors_and_cache(env, monkeypatch):
    prof = client.get("/api/profile").json()["profile"]
    prof["competitors"] = ["TestCo"]
    client.put("/api/profile", json=prof)

    cid = _research("Zen Finance One")
    d = client.get(f"/api/accounts/{cid}").json()
    assert d["run"]["status"] == "done", d["run"]
    assert calls["tavily"] == 1
    assert d["source_mix"] == {"jobs": 1, "vendor": 1}

    # Tech & vendors, with the competitor flagged.
    t = client.get(f"/api/accounts/{cid}/tech").json()
    v = {x["name"]: x for x in t["vendors"]}
    assert v["CoreSoft"]["relationship"] == "selected"
    assert v["TestCo"]["is_competitor"] == 1
    assert {x["name"] for x in t["tech"]} >= {"Playwright", "CoreSoft"}

    # Org chart: confirmed edge from the job post, inferred edges from titles.
    o = client.get(f"/api/accounts/{cid}/org").json()
    by_name = {n["name"]: n for n in o["nodes"]}
    edge = {(e["from"], e["to"]): e["kind"] for e in o["edges"]}
    assert edge[(by_name["Ravi Iyer"]["id"], by_name["Meena S"]["id"])] == "confirmed"
    assert edge[(by_name["Meena S"]["id"], by_name["Arun K"]["id"])] == "inferred"
    assert edge[(by_name["Arun K"]["id"], by_name["Dev P"]["id"])] == "inferred"
    assert edge[(by_name["Kiran M"]["id"], by_name["Ravi Iyer"]["id"])] == "inferred"
    assert by_name["Meena S"]["function"] == "Quality"
    assert any(i["role"] for i in by_name["Ravi Iyer"]["initiatives"])

    # Re-research within 24h re-uses cached sources: no new web search.
    client.post(f"/api/accounts/{cid}/refresh")
    assert calls["tavily"] == 1
    # force=true searches again.
    client.post(f"/api/accounts/{cid}/refresh?force=true")
    assert calls["tavily"] == 2


def test_feedback_loop(env):
    cid = _research("Zen Finance Two")
    d = client.get(f"/api/accounts/{cid}").json()
    init = d["initiatives"][0]
    contacts = {c["full_name"]: c for c in init["contacts"]}
    assert "Sam T" in contacts or "Dev P" in contacts or len(contacts) >= 2
    reject = next(c for c in init["contacts"] if c["full_name"] != "Ravi Iyer")
    keep = contacts["Ravi Iyer"]
    assert client.post(f"/api/contacts/{reject['id']}/feedback", json={"verdict": "rejected"}).json()["feedback"] == "rejected"
    client.post(f"/api/contacts/{keep['id']}/feedback", json={"verdict": "confirmed"})
    assert client.post(f"/api/contacts/{keep['id']}/feedback", json={"verdict": "nope"}).status_code == 400

    client.post(f"/api/accounts/{cid}/refresh")
    d2 = client.get(f"/api/accounts/{cid}").json()
    names = [c["full_name"] for c in d2["initiatives"][0]["contacts"]]
    assert reject["full_name"] not in names            # never suggested again
    assert names[0] == "Ravi Iyer"                     # confirmed person pinned first
    assert d2["initiatives"][0]["contacts"][0]["score"] == 1.0

    # Title learning carries across companies.
    with db.session() as s:
        stats = db.rows(s.execute("SELECT * FROM title_stats"))
    assert any(r["rejects"] >= 1 for r in stats) and any(r["confirms"] >= 1 for r in stats)

    # Dismissing an initiative hides it now and skips it on future runs.
    iid = d2["initiatives"][0]["id"]
    client.post(f"/api/initiatives/{iid}/feedback", json={"verdict": "dismissed"})
    assert client.get(f"/api/accounts/{cid}").json()["dismissed"] == 1
    client.post(f"/api/accounts/{cid}/refresh")
    d3 = client.get(f"/api/accounts/{cid}").json()
    assert d3["initiatives"] == []
    assert "dismissed earlier skipped" in " ".join(d3["run"]["log"])
    client.post(f"/api/accounts/{cid}/feedback", json={})  # unknown route -> 404/405, should not crash


def test_watch_and_alerts(env, monkeypatch):
    cid = _research("Zen Finance Three")
    assert client.post(f"/api/accounts/{cid}/watch", json={"watch": True}).json()["watch"] is True
    before = client.get("/api/alerts").json()["unread"]

    # Next check finds a new initiative, a new leader, a hiring surge.
    env["docs"] = DOCS_V2
    env["extract"] = {
        **EXTRACT_V1,
        "initiatives": EXTRACT_V1["initiatives"] + [
            {"name": "GenAI advisor", "category": "data_ai", "stage": "in_flight", "summary": "Launched GenAI advisor.",
             "tech": ["LLM"], "evidence": [{"doc": "KEY2", "quote": "launched a GenAI advisor"}],
             "people": [{"name": "Asha Rao", "title": "Head of AI", "involvement": "leads it", "reports_to": None}]}],
        "vendors": EXTRACT_V1["vendors"] + [{"name": "CloudCo", "relationship": "partner", "area": "hosting", "doc": "KEY2", "quote": "x"}],
    }
    # Pretend the last research was 8 days ago so the watchlist picks it up.
    with db.session() as s:
        s.execute("UPDATE company SET last_researched_at='2020-01-01 00:00:00' WHERE id=?", (cid,))
    assert cid in alerts.due_accounts()
    n = alerts.refresh_due(pipeline.run)
    assert n >= 1
    a = client.get(f"/api/alerts?company_id={cid}").json()["alerts"]
    kinds = {x["kind"] for x in a}
    assert {"new_initiative", "new_leader", "hiring_surge", "new_vendor"} <= kinds, kinds
    assert client.get("/api/alerts").json()["unread"] > before
    client.post("/api/alerts/read", json={"company_id": cid})
    assert client.get(f"/api/alerts?company_id={cid}&unread=true").json()["alerts"] == []


def test_org_inference_rules():
    assert orgchart.function_of("Director - Quality Engineering") == "Quality"
    assert orgchart.function_of("Chief Technology Officer") == "Engineering"
    assert orgchart.function_of("CISO") == "Security & risk"
    assert orgchart.rank_of("CEO") == 0 and orgchart.rank_of("CTO") == 1 and orgchart.rank_of("VP Engineering") == 2
    assert orgchart.rank_of("Head of QA") == 3 and orgchart.rank_of("QA Manager") == 5


def test_cache_expiry():
    cache.put("k", {"a": 1})
    assert cache.get("k", 1) == {"a": 1}
    with db.session() as s:
        s.execute("UPDATE cache SET fetched_at='2020-01-01 00:00:00' WHERE key='k'")
    assert cache.get("k", 1) is None


def test_migrates_old_database(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT NOT NULL, domain TEXT, industry TEXT,
        hq_country TEXT, summary TEXT, created_at TEXT, UNIQUE(name));
        CREATE TABLE person (id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, full_name TEXT NOT NULL, title TEXT,
        seniority TEXT, linkedin_url TEXT, apollo_id TEXT, email TEXT, phone TEXT, source TEXT, UNIQUE(company_id, full_name));
        INSERT INTO company(name) VALUES ('Old Co');""")
    con.close()
    monkeypatch.setattr(config, "DB_PATH", str(path))
    db.init()
    with db.session() as s:
        cols = {r["name"] for r in s.execute("PRAGMA table_info(company)")}
        assert {"watch", "last_researched_at"} <= cols
        assert s.execute("SELECT name FROM company").fetchone()["name"] == "Old Co"


def test_tavily_reads_full_pages(monkeypatch):
    sent = []

    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [{"url": "https://naukri.test/a", "title": "Zen Finance SDET", "content": "short",
                                 "raw_content": "Zen Finance full job description " * 20}]}

    monkeypatch.setattr(tavily.httpx, "post", lambda url, json, headers, timeout: sent.append(json) or R())
    docs = tavily.search("Zen Finance", "zen.test")
    assert all(b["include_raw_content"] for b in sent)
    assert any("naukri.com" in (b.get("include_domains") or []) for b in sent)
    assert any(b.get("include_domains") == ["zen.test"] for b in sent)   # careers pages on the company's site
    assert docs[0]["text"].startswith("Zen Finance full job description")


def test_consolidate_merges_job_posts_into_projects(monkeypatch):
    cands = [
        {"name": "Snowflake QA Engineering Hiring", "category": "qa_testing", "stage": "hiring", "summary": "Hiring QA for Snowflake ETL.",
         "tech": ["Snowflake"], "evidence": [{"doc": "doc1", "quote": "Senior QA Engineer"}], "people": []},
        {"name": "Enterprise data platform on Snowflake", "category": "data_ai", "stage": "announced", "summary": "Moving analytics to Snowflake.",
         "tech": ["Snowflake", "dbt"], "evidence": [{"doc": "doc2", "quote": "moving analytics to Snowflake"}],
         "people": [{"name": "Priya N", "title": "Head of Data", "involvement": "leads it"}]},
        {"name": "Member app relaunch", "category": "app_launch", "stage": "announced", "summary": "New app.", "tech": [],
         "evidence": [{"doc": "doc3", "quote": "new app"}], "people": []},
    ]
    monkeypatch.setattr(pipeline.llm, "complete_json", lambda *a, **k: {"projects": [
        {"name": "Snowflake data platform build-out", "category": "data_ai", "stage": "hiring", "summary": "Analytics moving to Snowflake; hiring QA for ETL testing.", "members": [0, 1]},
        {"name": "Member app relaunch", "category": "app_launch", "stage": "announced", "summary": "New app.", "members": [2]},
    ]})
    out = pipeline.consolidate({"name": "Acme"}, cands)
    assert [p["name"] for p in out] == ["Snowflake data platform build-out", "Member app relaunch"]
    snow = out[0]
    assert len(snow["evidence"]) == 2 and snow["people"][0]["name"] == "Priya N" and "dbt" in snow["tech"]

    docs = {"doc1": {"source_type": "jobs"}, "doc2": {"source_type": "news"}}
    assert pipeline.basis_of(snow, docs) == "announced"
    assert pipeline.basis_of({"evidence": [{"doc": "doc1"}]}, docs) == "hiring"

    # If the LLM fails, fall back to name clustering instead of losing candidates.
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(pipeline.llm, "complete_json", boom)
    assert len(pipeline.consolidate({"name": "Acme"}, cands)) == 3


def test_extraction_errors_are_reported(env, monkeypatch):
    def boom(system, prompt, *a, **k):
        if "profile companies" in system:
            return {"industry": "X"}
        raise RuntimeError("OpenAI API error 404: model not found")
    monkeypatch.setattr(pipeline.llm, "complete_json", boom)
    cid = client.post("/api/accounts", json={"name": "Zen Finance Four", "domain": "zen.test"}).json()["company_id"]
    run = client.get(f"/api/accounts/{cid}").json()["run"]
    assert run["status"] == "failed"
    assert "model not found" in run["error"] and "backend.doctor" in run["error"]


def test_messy_dates_and_tech_do_not_crash(env, monkeypatch):
    env["docs"] = [dict(DOCS_V1[0], published_at="Mon, 20 Oct 2026 10:00:00 GMT"),
                   dict(DOCS_V1[1], published_at="not a date")]
    env["extract"] = {**EXTRACT_V1, "initiatives": [dict(EXTRACT_V1["initiatives"][0], tech=["Snowflake", None, "", "SQL"])]}
    cid = client.post("/api/accounts", json={"name": "Zen Finance Five", "domain": "zen.test"}).json()["company_id"]
    d = client.get(f"/api/accounts/{cid}").json()
    assert d["run"]["status"] == "done", d["run"]
    assert d["initiatives"][0]["tech"] == ["SQL", "Snowflake"]
    assert d["initiatives"][0]["last_seen"] == "2026-10-20"
    assert pipeline.norm_date("2026-10-20T08:00:00Z") == "2026-10-20"
    assert pipeline.norm_date("20 October 2026") == "2026-10-20"
    assert pipeline.norm_date(None) is None


DEALS_AND_SITES = {
    "vendors": [{"name": "Infosys", "relationship": "selected", "area": "core banking implementation", "deal_type": "new",
                 "value": "$120 million", "date": "2026-05", "duration": "5 years", "doc": "KEY1", "quote": "five-year $120 million deal"},
                {"name": "OldVendor", "relationship": "replacing", "area": "app support", "deal_type": "ended", "value": None,
                 "date": None, "duration": None, "doc": "KEY1", "quote": "replacing OldVendor"}],
    "locations": [{"city": "chennai", "country": "India", "type": "gcc", "functions": ["engineering", "QA"], "headcount": "2,500",
                   "doc": "KEY1", "quote": "2,500-person tech centre in Chennai"},
                  {"city": "Austin", "country": "United States", "type": "hq", "functions": [], "headcount": None, "doc": "KEY1", "quote": "HQ"}],
    "job_locations": [{"city": "Chennai", "country": "India", "function": "QA"}, {"city": "Chennai", "country": "India", "function": "data"},
                      {"city": "Pune", "country": "India", "function": "engineering"}],
}


def test_deals_and_footprint(env):
    env["extract"] = {**EXTRACT_V1, **DEALS_AND_SITES}
    cid = client.post("/api/accounts", json={"name": "Zen Finance Six", "domain": "zen.test"}).json()["company_id"]
    assert client.get(f"/api/accounts/{cid}").json()["run"]["status"] == "done"
    v = client.get(f"/api/accounts/{cid}/tech").json()["vendors"]
    infy = next(x for x in v if x["name"] == "Infosys")
    assert (infy["deal_type"], infy["deal_value"], infy["deal_date"], infy["duration"]) == ("new", "$120 million", "2026-05", "5 years")
    old = next(x for x in v if x["name"] == "OldVendor")
    assert old["deal_type"] == "ended" and old["deal_date"] == "2026-09-10"   # falls back to the source's date
    f = client.get(f"/api/accounts/{cid}/footprint").json()
    sites = {(s["city"], s["type"]): s for s in f["sites"]}
    assert sites[("Chennai", "gcc")]["headcount"] == 2500 and "QA" in sites[("Chennai", "gcc")]["functions"]
    assert f["sites"][0]["type"] == "hq"
    hiring = {h["city"]: h for h in f["hiring"]}
    assert hiring["Chennai"]["roles"] == 2 and set(hiring["Chennai"]["functions"]) == {"qa", "data"}
    assert f["hiring"][0]["city"] == "Chennai"
    client.delete(f"/api/accounts/{cid}")
    with db.session() as s:
        assert s.execute("SELECT COUNT(*) n FROM location WHERE company_id=?", (cid,)).fetchone()["n"] == 0


def test_buyer_brief(env, monkeypatch):
    from backend import buyers
    cid = client.post("/api/accounts", json={"name": "Zen Finance Seven", "domain": "zen.test"}).json()["company_id"]
    d = client.get(f"/api/accounts/{cid}").json()
    ravi = next(c for i in d["initiatives"] for c in i["contacts"] if c["full_name"] == "Ravi Iyer")
    assert not ravi["has_brief"]
    searched = []

    def fake_raw(q, topic="general", days=None, max_results=10, include_domains=None, full_text=False):
        searched.append(q)
        return [{"url": f"https://talks.test/{len(searched)}", "title": "Ravi Iyer on modernising lending",
                 "published_at": "2026-08-01", "text": "Ravi Iyer, CTO at Zen Finance: we will not compromise on release quality; speed matters."},
                {"url": "https://other.test/x", "title": "Unrelated", "published_at": None, "text": "Someone else entirely."}]

    monkeypatch.setattr(buyers.tavily, "raw_search", fake_raw)
    monkeypatch.setattr(buyers.llm, "complete_json", lambda system, prompt, *a, **k: {
        "summary": "CTO focused on modernising lending.", "priorities": ["release quality", "speed"],
        "communication_style": "pragmatic", "style_note": "Talks in outcomes.", "motivators": ["faster releases"],
        "concerns": ["quality slips"], "approach": ["Lead with release-quality metrics"], "avoid": ["generic pitches"],
        "talking_points": ["Automation for the lending platform"], "evidence": [{"source": 0, "quote": "will not compromise on release quality"}],
        "confidence": "medium"} if "buyer briefs" in system else {})
    b = client.post(f"/api/people/{ravi['person_id']}/brief").json()
    assert b["communication_style"] == "pragmatic" and b["priorities"][0] == "release quality"
    assert all("other.test" not in s["url"] for s in b["sources"])   # sources not mentioning the person are dropped
    n = len(searched)
    client.post(f"/api/people/{ravi['person_id']}/brief")            # cached: no new searches
    assert len(searched) == n
    assert client.get(f"/api/people/{ravi['person_id']}/brief").json()["confidence"] == "medium"
    assert next(c for i in client.get(f"/api/accounts/{cid}").json()["initiatives"] for c in i["contacts"]
                if c["full_name"] == "Ravi Iyer")["has_brief"] == 1

    # Hidden surnames must be revealed first.
    with db.session() as s:
        pid = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Neelima An***m', 'CIO')", (cid,)).lastrowid
    r = client.post(f"/api/people/{pid}/brief")
    assert r.status_code == 400 and "Get email" in r.json()["detail"]


def test_free_website_tech_detection(env, monkeypatch):
    from backend.providers import webtech
    html = ('<html><head><meta name="generator" content="WordPress 6.4"><script src="https://www.googletagmanager.com/gtag/js?id=G-1">'
            '</script></head><body></body></html>')
    calls = []
    monkeypatch.setattr(webtech, "fetch", lambda domain: calls.append(domain) or ("https://zen.test", html, {"Server": "cloudflare"}))
    techs = {t["name"]: t["category"] for t in webtech.lookup("zen-web.test")}
    assert "WordPress 6.4" in techs and "CMS" in techs["WordPress 6.4"]
    assert "Cloudflare" in techs and "Google Tag Manager" in techs
    webtech.lookup("zen-web.test")
    assert calls == ["zen-web.test"]   # cached after the first lookup

    cid = client.post("/api/accounts", json={"name": "Zen Finance Eight", "domain": "zen-web.test"}).json()["company_id"]
    t = client.get(f"/api/accounts/{cid}/tech").json()["tech"]
    assert any(x["source"] == "website" and x["name"] == "WordPress 6.4" for x in t)
