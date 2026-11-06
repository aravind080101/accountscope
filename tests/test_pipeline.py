"""API-level tests. External services (Tavily, Claude, Apollo) are replaced by stand-in
responses so the tests run offline; the app itself ships no sample data."""
import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import config, pipeline  # noqa: E402
from backend.app import app  # noqa: E402
from backend.providers import apollo, tavily  # noqa: E402

client = TestClient(app, headers={"X-Requested-With": "accountscope"})

DOCS = [
    {"source_type": "jobs", "url": "https://careers.test/sdet", "title": "Senior SDET - Core Banking", "published_at": "2026-10-12",
     "text": "Hiring 12 SDETs for the Core Banking Transformation programme. You will report to A. Rao, Director - Quality Engineering." * 2},
    {"source_type": "news", "url": "https://news.test/core", "title": "Bank picks new core", "published_at": "2026-08-30",
     "text": "The bank selected a new core banking platform, said CTO V. Sethi. A testing partner is yet to be named." * 2},
    {"source_type": "news", "url": "https://news.test/ciso", "title": "Cyber programme", "published_at": "2026-09-05",
     "text": "The bank launched a cyber resilience programme, CISO F. Ali said, covering application security testing." * 2},
]

LLM = {
    "describe": {"industry": "Banking", "hq_country": "India", "domain": "bank.test", "summary": "A bank."},
    "extract": {"initiatives": [
        {"name": "Core banking replacement", "category": "app_modernization", "stage": "hiring",
         "summary": "New core; testing partner not yet named.", "tech": ["playwright", "migration"],
         "evidence": [{"doc": "doc1", "quote": "Hiring 12 SDETs"}],
         "people": [{"name": "A. Rao", "title": "Director - Quality Engineering", "involvement": "hiring manager for the SDETs"}]},
        {"name": "Core banking transformation programme", "category": "app_modernization", "stage": "announced",
         "summary": "Selected a new core.", "tech": ["core banking"],
         "evidence": [{"doc": "doc2", "quote": "selected a new core banking platform"}],
         "people": [{"name": "V. Sethi", "title": "CTO", "involvement": "public sponsor"}]},
        {"name": "Cyber resilience programme", "category": "cybersecurity", "stage": "announced",
         "summary": "Application security testing.", "tech": ["security"],
         "evidence": [{"doc": "doc3", "quote": "launched a cyber resilience programme"}],
         "people": [{"name": "F. Ali", "title": "CISO", "involvement": "leads the programme"}]},
    ]},
}

PEOPLE = [
    {"full_name": "A. Rao", "title": "Director - Quality Engineering", "seniority": "director", "linkedin_url": "https://li.test/arao", "apollo_id": "p1"},
    {"full_name": "L. Varma", "title": "Chief Information Officer", "seniority": "c_suite", "linkedin_url": None, "apollo_id": "p2"},
    {"full_name": "R. Bhatia", "title": "AppSec Lead", "seniority": "senior", "linkedin_url": None, "apollo_id": "p3"},
    {"full_name": "S. Pillai", "title": "Head of Sales", "seniority": "head", "linkedin_url": None, "apollo_id": "p4"},
]


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(config, "TAVILY_API_KEY", "test")
    monkeypatch.setattr(config, "APOLLO_API_KEY", "test")
    monkeypatch.setattr(tavily, "search", lambda name, domain=None: [dict(d) for d in DOCS])
    def fake_json(system, prompt, *a, **k):
        if "profile companies" in system:
            return LLM["describe"]
        # The stand-in extraction refers to DOCS by position (doc1, doc2...); map to real stored keys.
        from backend import db
        import json as _j
        with db.session() as s:
            ids = {r["url"]: r["id"] for r in s.execute("SELECT id, url FROM document")}
        text = _j.dumps(LLM["extract"])
        for n, d in enumerate(DOCS, 1):
            text = text.replace(f'"doc{n}"', f'"__D{ids[d["url"]]}"')
        return _j.loads(text.replace('"__D', '"doc'))

    monkeypatch.setattr(pipeline.llm, "complete_json", fake_json)
    monkeypatch.setattr(pipeline.llm, "complete", lambda *a, **k: "Hi, short note.")
    monkeypatch.setattr(pipeline.llm, "available", lambda: True)
    monkeypatch.setattr(apollo, "search_people", lambda domain, titles, per_page=10: [dict(p) for p in PEOPLE])
    from backend.providers import webtech
    monkeypatch.setattr(webtech, "fetch", lambda domain: None)
    monkeypatch.setattr(apollo, "enrich", lambda aid, name, domain: {"email": "arao@bank.test", "phone": None, "linkedin_url": None})


def test_requires_keys(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    h = client.get("/api/health").json()
    assert h["configured"] is False and "ANTHROPIC_API_KEY or OPENAI_API_KEY" in h["missing_keys"]
    r = client.post("/api/accounts", json={"name": "Any Company"})
    assert r.status_code == 400 and "OPENAI_API_KEY" in r.json()["detail"]


def test_research_real_company_flow(connected):
    cid = client.post("/api/accounts", json={"name": "Example Bank", "domain": "https://www.bank.test/"}).json()["company_id"]
    d = client.get(f"/api/accounts/{cid}").json()
    assert d["run"]["status"] == "done", (d["run"], d["run"].get("error") if isinstance(d["run"], dict) else None)
    assert d["company"]["industry"] == "Banking" and d["company"]["domain"] == "bank.test"
    assert len(d["initiatives"]) == 2  # the two core-banking candidates merged
    core = next(i for i in d["initiatives"] if i["category"] == "app_modernization")
    assert len(core["evidence"]) == 2
    roles = {c["full_name"]: (c["role"], c["source"]) for c in core["contacts"]}
    assert roles["A. Rao"] == ("Owner", "evidence")
    assert roles["V. Sethi"] == ("Sponsor", "evidence")
    assert roles["L. Varma"] == ("Sponsor", "apollo")
    assert "S. Pillai" not in roles  # unrelated title filtered out
    sec = next(i for i in d["initiatives"] if i["category"] == "cybersecurity")
    assert sec["contacts"][0]["full_name"] == "F. Ali" and sec["contacts"][0]["role"] == "Owner"
    # Apollo details merged into the evidence-named person.
    assert core["contacts"][0]["linkedin_url"] == "https://li.test/arao"
    csv = client.get(f"/api/accounts/{cid}/export.csv").text
    assert "A. Rao" in csv and "https://careers.test/sdet" in csv
    e = client.post(f"/api/contacts/{core['contacts'][0]['id']}/enrich").json()
    assert e["email"] == "arao@bank.test"


def test_bulk_queue(connected):
    r = client.post("/api/accounts/bulk", json={"companies": [{"name": "Alpha Ltd"}, {"name": "Beta Inc", "domain": "beta.test"}, {"name": " "}]})
    assert r.json()["queued"] == 2
    for cid in r.json()["company_ids"]:
        assert client.get(f"/api/accounts/{cid}").json()["run"]["status"] == "done"


def test_no_documents_fails_clearly(connected, monkeypatch):
    monkeypatch.setattr(tavily, "search", lambda name, domain=None: [])
    cid = client.post("/api/accounts", json={"name": "Nonexistent Co"}).json()["company_id"]
    run = client.get(f"/api/accounts/{cid}").json()["run"]
    assert run["status"] == "failed" and "No public documents" in run["error"]


def test_classify_titles():
    assert pipeline.classify("Head of QA & Automation", "qa_testing")[0] == "Owner"
    assert pipeline.classify("Chief Technology Officer", "qa_testing")[0] == "Sponsor"
    assert pipeline.classify("SDET Lead", "qa_testing")[0] == "Practitioner"
    assert pipeline.classify("CISO", "cybersecurity")[0] == "Owner"


def test_openai_provider(monkeypatch):
    from backend import llm

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(config, "TAVILY_API_KEY", "t")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    assert config.llm_provider() == "openai" and config.configured()
    sent = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '```json\n{"initiatives": []}\n```'}}]}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, body=json, headers=headers)
        return Resp()

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.complete_json("sys", "prompt") == {"initiatives": []}
    assert sent["url"].endswith("/v1/chat/completions")
    assert sent["body"]["model"] == config.OPENAI_MODEL
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert sent["headers"]["Authorization"] == "Bearer sk-test"
    h = client.get("/api/health").json()
    assert h["llm_provider"] == "openai" and h["configured"]


def test_provider_preference(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "a")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "o")
    monkeypatch.setattr(config, "LLM_PROVIDER", "")
    assert config.llm_provider() == "anthropic"
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    assert config.llm_provider() == "openai"


def test_signal_radar(connected, monkeypatch):
    from backend import discover

    monkeypatch.setattr(tavily, "raw_search", lambda q, topic="general", days=None, max_results=10: [
        {"url": "https://news.test/a", "title": "Acme hires 40 SDETs", "published_at": "2026-10-30", "text": "Acme is hiring 40 SDETs."},
        {"url": "https://news.test/a", "title": "dup", "published_at": None, "text": "dup"},
        {"url": "https://news.test/b", "title": "Example Bank QA push", "published_at": "2026-10-28", "text": "Example Bank QA team grows."},
    ])
    monkeypatch.setattr(discover.llm, "complete_json", lambda *a, **k: {"companies": [
        {"company": "Acme", "domain": "acme.test", "country": "India", "signal": "Hiring 40 SDETs.", "source": 0},
        {"company": "acme", "signal": "duplicate", "source": 0},
        {"company": "Example Bank", "signal": "Growing QA team.", "source": 1},
    ]})
    r = client.post("/api/discover/signals", json={"preset": "qa_hiring", "region": "India", "days": 30}).json()
    names = [c["name"] for c in r["companies"]]
    assert names == ["Acme", "Example Bank"]
    assert r["companies"][0]["source_url"] == "https://news.test/a"
    # Example Bank was researched in an earlier test, so it links to the existing account.
    assert r["companies"][1]["account_id"] is not None
    assert client.post("/api/discover/signals", json={}).status_code == 400


def test_browse_companies(connected, monkeypatch):
    seen = {}

    def fake_search(keywords, locations, sizes, page=1, per_page=25):
        seen.update(keywords=keywords, locations=locations, sizes=sizes, page=page)
        return {"companies": [{"name": "Zeta Corp", "domain": "zeta.test", "industry": "Banking", "employees": 5000,
                               "country": "India", "city": "Mumbai", "linkedin_url": None}], "page": page, "total_pages": 3, "total": 61}

    monkeypatch.setattr(apollo, "search_companies", fake_search)
    r = client.post("/api/discover/companies", json={"keywords": "banking, fintech", "location": "India", "size": "1001-5000", "page": 2}).json()
    assert seen == {"keywords": ["banking", "fintech"], "locations": ["India"], "sizes": ["1001,5000"], "page": 2}
    assert r["companies"][0]["name"] == "Zeta Corp" and r["total"] == 61
    monkeypatch.setattr(config, "APOLLO_API_KEY", "")
    assert client.post("/api/discover/companies", json={}).status_code == 400
