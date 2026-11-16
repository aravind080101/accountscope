"""Campaigns: their own decks, profile, company search and outreach, kept apart from the general library."""
from fastapi.testclient import TestClient

from backend import app as appmod, campaigns, db, discover, pitch, profiles

H = {"X-Requested-With": "accountscope"}
BANK_DECK = ("Core banking migration assurance for banks: we reconcile standing instructions, beneficiaries and limits per "
             "customer before cutover. Case study: a mid-size Indian bank moved 4 million accounts with zero failed mandates. ") * 3
GENERAL_DECK = "Device lab testing for mobile apps across 2,000 real devices, accessibility audits and performance testing. " * 3


def _client(monkeypatch):
    monkeypatch.setattr(appmod.llm, "available", lambda: True)
    monkeypatch.setattr(appmod, "_require_keys", lambda: None)
    return TestClient(appmod.app, headers=H)


def test_campaign_decks_stay_out_of_the_general_library(monkeypatch):
    c = _client(monkeypatch)
    camp = c.post("/api/campaigns", json={"name": "Banking Q1", "description": "Indian banks moving cores"}).json()
    profiles.add_source("general.pdf", "deck", GENERAL_DECK)
    profiles.add_source("bank-migration.pdf", "deck", BANK_DECK, campaign_id=camp["id"])
    general = [s["name"] for s in profiles.list_sources()]
    assert "general.pdf" in general and "bank-migration.pdf" not in general
    assert [s["name"] for s in c.get(f"/api/campaigns/{camp['id']}").json()["sources"]] == ["bank-migration.pdf"]
    # deck search is scoped too
    q = "core banking migration standing instructions beneficiaries cutover"
    assert profiles.relevant_material(q) == []
    assert profiles.relevant_material(q, campaign_id=camp["id"])[0]["doc"] == "bank-migration.pdf"
    listed = {x["name"]: x for x in c.get("/api/campaigns").json()}
    assert listed["Banking Q1"]["docs"] == 1


def test_campaign_profile_search_and_accounts(monkeypatch):
    c = _client(monkeypatch)
    camp = c.post("/api/campaigns", json={"name": "Core moves"}).json()
    profiles.add_source("deck.pdf", "deck", BANK_DECK, campaign_id=camp["id"])
    monkeypatch.setattr(campaigns.llm, "complete_json", lambda system, prompt, *a, **k: {
        "description": "Migration assurance for banks.",
        "offerings": [{"name": "Migration Assurance", "kind": "service", "what": "Cutover testing", "problems": ["core move"], "buyers": ["CIO"]}],
        "proof": ["4 million accounts moved"], "offers": [], "buyer_titles": ["CIO"], "target_industries": ["Banking"],
        "target_regions": ["India"], "search_signals": ["bank announces core banking migration", "bank new net banking platform"],
        "search_keywords": ["banking"]} if "MATERIAL" in prompt else {})
    built = c.post(f"/api/campaigns/{camp['id']}/profile").json()
    assert built["profile"]["offerings"][0]["name"] == "Migration Assurance"

    seen = []

    def fake_radar(preset, query, region=None, days=30):
        seen.append(query)
        return [{"name": "City Union Bank", "domain": "cityunionbank.com", "signal": f"Doing: {query}", "source_url": "https://x.test",
                 "account_id": None}]
    monkeypatch.setattr(discover, "signal_radar", fake_radar)
    found = c.post(f"/api/campaigns/{camp['id']}/find", json={"region": ["India"], "days": 30}).json()
    assert seen == ["bank announces core banking migration", "bank new net banking platform"]
    assert len(found["companies"]) == 1 and len(found["companies"][0]["matched"]) == 2    # merged across searches

    monkeypatch.setattr(appmod.pipeline, "run", lambda *a, **k: None)
    r = c.post(f"/api/campaigns/{camp['id']}/accounts", json={"companies": [
        {"name": "City Union Bank", "domain": "cityunionbank.com", "signal": "core move", "source_url": "https://x.test"}]}).json()
    assert r["linked"] == 1 and r["researching"] == 1
    acc = r["campaign"]["accounts"][0]
    assert acc["name"] == "City Union Bank" and acc["signal"] == "core move"

    # campaign profile for pitches: campaign offerings, general identity
    p = campaigns.profile_for(camp["id"])
    assert [o["name"] for o in p["offerings"]] == ["Migration Assurance"] and p["campaign"]["name"] == "Core moves"
    assert p["company"] == profiles.load()["company"]


def test_campaign_pitch_does_not_replace_the_general_one():
    with db.session() as s:
        cid = s.execute("INSERT INTO company(name) VALUES ('Two Pitch Co')").lastrowid
        pid = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Meera Iyer', 'CIO')", (cid,)).lastrowid
        camp = s.execute("INSERT INTO campaign(workspace_id, name) VALUES (1, 'Camp A')").lastrowid
    general = pitch.create(pid)
    in_camp = pitch.create(pid, campaign_id=camp)
    again = pitch.create(pid, campaign_id=camp)          # replaces only the campaign one
    with db.session() as s:
        rows = [dict(r) for r in s.execute("SELECT id, campaign_id FROM pitch WHERE person_id=?", (pid,))]
    assert len(rows) == 2 and {r["campaign_id"] for r in rows} == {None, camp} and in_camp      # one general + one campaign
    assert general in {r["id"] for r in rows}
    assert {p["id"] for p in pitch.list_all(cid, 1, campaign_id=camp)} == {again}
    assert {p["id"] for p in pitch.list_all(cid, 1, general_only=True)} == {general}
    assert pitch.get(again)["campaign"] == "Camp A"
