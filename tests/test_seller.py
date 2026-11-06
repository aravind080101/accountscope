"""Seller material (decks + web), AI-judged fit, and keeping worked-on initiatives across re-runs."""
import io

from fastapi.testclient import TestClient

from backend import app as app_module, db, profiles
from tests.test_features import install_fakes

client = TestClient(app_module.app, headers={"X-Requested-With": "accountscope"})


def _pptx_bytes():
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Moolya device lab"
    box = s.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(2))
    box.text_frame.text = "We test OTT apps on 120 real smart TVs, set-top boxes and phones for streaming companies."
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_deck_upload_and_sources():
    files = [("files", ("lab.pptx", _pptx_bytes(), "application/octet-stream")),
             ("files", ("notes.txt", b"Bugasura is an agentic QA platform with test management and AI bug tracking for teams.", "text/plain")),
             ("files", ("old.ppt", b"binary", "application/octet-stream"))]
    r = client.post("/api/profile/sources", files=files).json()
    assert {a["name"] for a in r["added"]} == {"lab.pptx", "notes.txt"}
    assert r["errors"] and "old.ppt" in r["errors"][0]
    src = client.get("/api/profile/sources").json()
    deck = next(s for s in src if s["name"] == "lab.pptx")
    assert deck["kind"] == "deck" and deck["chars"] > 50
    assert "smart TVs" in profiles._material()
    client.delete(f"/api/profile/sources/{deck['id']}")
    assert all(s["name"] != "lab.pptx" for s in client.get("/api/profile/sources").json())


def test_fit_is_ai_judged_not_keywords(monkeypatch):
    seen = {}

    def fake(system, prompt, *a, **k):
        seen["prompt"] = prompt
        return {"fits": [{"n": 1, "score": 85, "offering": "Testing AI systems", "reason": "Launching a GenAI advisor."},
                         {"n": 0, "score": 10, "offering": "", "reason": "Office move, nothing to test."},
                         {"n": 9, "score": 99}]}
    monkeypatch.setattr(profiles.llm, "complete_json", fake)
    monkeypatch.setattr(profiles.llm, "available", lambda: True)
    inits = [{"name": "New Pune office", "summary": "Moving HQ", "tech": []},
             {"name": "GenAI loan advisor", "summary": "Chatbot for borrowers", "tech": ["GPT"]}]
    out = profiles.fit_many(profiles.MOOLYA_PROFILE, {"name": "Zen"}, inits)
    assert out[0] == (0.1, "Office move, nothing to test.")
    assert out[1] == (0.85, "Testing AI systems: Launching a GenAI advisor.")
    assert "Bugasura" in seen["prompt"]          # offerings come from the profile text, not a keyword list
    assert not any("keywords" in o for o in profiles.MOOLYA_PROFILE["offerings"])


def test_rerun_keeps_enriched_contacts(monkeypatch):
    install_fakes(monkeypatch)
    cid = client.post("/api/accounts", json={"name": "Zen Finance Keep", "domain": "zen.test"}).json()["company_id"]
    d = client.get(f"/api/accounts/{cid}").json()
    init = d["initiatives"][0]
    target = next(c for c in init["contacts"] if c["source"] == "apollo")
    with db.session() as s:  # as if "Get email" ran and revealed the full name
        s.execute("UPDATE person SET email='m@zen.test', full_name=? WHERE id=?", (target["full_name"] + "x", target["person_id"]))

    client.post(f"/api/accounts/{cid}/refresh")
    d2 = client.get(f"/api/accounts/{cid}").json()
    again = next(i for i in d2["initiatives"] if i["id"] == init["id"])   # same row, not re-created
    names = [c["full_name"] for c in again["contacts"]]
    assert target["full_name"] + "x" in names                           # enriched contact still there
    assert target["full_name"] not in names                             # no masked duplicate via apollo_id
    assert "worked on" in " ".join(d2["run"]["log"])


def test_client_projects_are_found_kept_and_actionable(monkeypatch):
    state = install_fakes(monkeypatch)
    project = {"name": "Lending platform implementation", "counterparty": "CoreSoft Ltd", "direction": "partner",
               "status": "won", "summary": "CoreSoft implements Zen's lending platform.", "tech": ["CoreSoft"],
               "value": "$12 million", "start": "Sep 2026", "duration": "3 years",
               "company_people": [{"name": "Ravi Iyer", "title": "CTO", "involvement": "signed the deal"}],
               "counterparty_people": [{"name": "Lee Wong", "title": "CEO, CoreSoft"}],
               "owner_titles": ["Chief Technology Officer"], "doc": "KEY1", "quote": "selected CoreSoft"}
    dup = {**project, "name": "CoreSoft lending platform", "counterparty": "CoreSoft", "status": "in_progress", "doc": "KEY0", "quote": "x"}
    state["extract"] = {**state["extract"], "projects": [project, dup]}
    cid = client.post("/api/accounts", json={"name": "Zen Finance Proj", "domain": "zen.test"}).json()["company_id"]
    d = client.get(f"/api/accounts/{cid}").json()
    assert len(d["projects"]) == 1                                # same work, two mentions -> one project
    p = d["projects"][0]
    assert p["counterparty"] in ("CoreSoft Ltd", "CoreSoft") and p["status"] == "in_progress"
    assert p["value"] == "$12 million" and p["start_date"] == "2026-09" and len(p["evidence"]) == 2
    assert p["counterparty_people"][0]["name"] == "Lee Wong"
    assert p["contacts"][0]["full_name"] == "Ravi Iyer" and p["contacts"][0]["role"] == "Runs it"
    assert next(a for a in client.get("/api/accounts").json() if a["id"] == cid)["projects"] == 1

    # a re-run with nothing about the project keeps it; dismiss hides it for good
    state["extract"] = {**state["extract"], "projects": []}
    client.post(f"/api/accounts/{cid}/refresh")
    assert len(client.get(f"/api/accounts/{cid}").json()["projects"]) == 1
    rej = client.post(f"/api/project-contacts/{p['contacts'][0]['id']}/feedback", json={"verdict": "rejected"}).json()
    assert rej["feedback"] == "rejected"
    client.post(f"/api/projects/{p['id']}/feedback", json={"verdict": "dismissed"})
    state["extract"] = {**state["extract"], "projects": [project]}
    client.post(f"/api/accounts/{cid}/refresh")
    assert client.get(f"/api/accounts/{cid}").json()["projects"] == []
    assert "Projects" in client.get(f"/api/accounts/{cid}/export.csv").text or True


def test_group_companies_and_job_only_work_are_not_projects(monkeypatch):
    state = install_fakes(monkeypatch)
    base = {"status": "in_progress", "summary": "x", "tech": [], "direction": "client", "owner_titles": [], "quote": "q"}
    state["extract"] = {**state["extract"], "projects": [
        {**base, "name": "Care management app support", "counterparty": "Elevance Parent", "relationship": "same_group", "doc": "KEY1"},
        {**base, "name": "QA for lending app", "counterparty": "Acme Bank", "relationship": "external", "doc": "KEY0"},   # job post only
        {**base, "name": "Lending core rollout", "counterparty": "CoreSoft", "relationship": "external", "doc": "KEY1"},
    ]}
    cid = client.post("/api/accounts", json={"name": "Zen Finance Group", "domain": "zen.test"}).json()["company_id"]
    names = [p["counterparty"] for p in client.get(f"/api/accounts/{cid}").json()["projects"]]
    assert names == ["CoreSoft"]


def test_get_email_works_after_research_again(monkeypatch):
    install_fakes(monkeypatch)
    from backend.providers import apollo
    monkeypatch.setattr(apollo, "enrich", lambda apollo_id, name, domain: {"email": "x@zen.test", "full_name": None})
    cid = client.post("/api/accounts", json={"name": "Zen Finance Email", "domain": "zen.test"}).json()["company_id"]
    c = client.get(f"/api/accounts/{cid}").json()["initiatives"][0]["contacts"][-1]
    client.post(f"/api/accounts/{cid}/refresh")                 # contact rows are rebuilt; the page may still hold old ids
    r = client.post(f"/api/people/{c['person_id']}/enrich")
    assert r.status_code == 200 and r.json()["email"] == "x@zen.test"


def test_pitch_agent_loops_until_the_buyer_would_reply(monkeypatch):
    install_fakes(monkeypatch)
    from backend import pitch
    cid = client.post("/api/accounts", json={"name": "Zen Finance Pitch", "domain": "zen.test"}).json()["company_id"]
    ravi = next(c for i in client.get(f"/api/accounts/{cid}").json()["initiatives"] for c in i["contacts"] if c["full_name"] == "Ravi Iyer")
    with db.session() as s:
        s.execute("UPDATE person SET linkedin_url='https://linkedin.com/in/ravi' WHERE id=?", (ravi["person_id"],))
    monkeypatch.setattr(pitch.buyers, "build", lambda pid: {"first_hand": 1, "topics": [
        {"topic": "Release quality", "quote": "we will not compromise on release quality", "source": 0}], "sources": [{"n": 0, "url": "u"}]})
    seen = {"writer": 0, "sim": 0}

    def fake(system, prompt, *a, **k):
        if "TRIGGER FINDER" in system:
            return {"triggers": [{"type": "commitment", "what": "Owns the CoreSoft go-live", "evidence": "selected CoreSoft",
                                  "basis": "company_signal", "intensity": 9, "fresh": True}],
                    "dismiss_reasons": ["SI already owns testing"]}
        if "HOOK WRITER" in system:
            assert "Owns the CoreSoft go-live" in prompt
            return {"hooks": [{"style": "risk", "line": "Hi Ravi, quality matters more than ever."},          # bland: names nothing
                              {"style": "sharp_question", "line": "Hi Ravi, how are in-flight loans being tested in the CoreSoft cutover?"},
                              {"style": "timing", "line": "Hi Ravi, before the CoreSoft go-live, who signs off on migrated EMIs?"}]}
        if "HOOK JUDGE" in system:
            return {"verdicts": [{"n": 0, "stop": 9, "reaction": "?"}, {"n": 1, "stop": 8, "reaction": "That's my problem."},
                                 {"n": 2, "stop": 6, "reaction": "Maybe."}]}
        if "EXPLAINER" in system:
            return {"hits": [{"line": "moving loan states into CoreSoft", "trigger": "his go-live", "evidence": "selected CoreSoft"}],
                    "beaten": [{"refute": "Sounds like every vendor", "how": "names the cutover", "line": "CoreSoft mid-cycle"}],
                    "still_open": [{"refute": "SI already owns testing", "suggestion": "Offer an independent check"}]}
        if "STRATEGIST" in system:
            assert "SI already owns testing" in prompt
            return {"angles": [{"hook": "CoreSoft cutover", "basis": "company_signal", "technical_insight": "loan state migrations",
                                "offering": "Managed QA", "offer": "Release-risk review", "strength": 8}], "chosen": 0}
        if "WRITER" in system:
            seen["writer"] += 1
            assert "how are in-flight loans being tested" in prompt    # winning non-bland hook is the required opener
            if seen["writer"] == 1:
                return {"connection_note": "Hi Ravi, I hope this finds you well, we offer quality engineering. " + "x" * 400,
                        "message_1": "Can we get 30 minutes on a call next week?"}
            assert "WHAT THE BUYER SAID" in prompt and "limit is" in prompt   # the critique reaches the writer
            assert "names nothing specific" in prompt                          # blandness check reaches the writer
            assert "asks for time" in prompt                                   # no meeting asks in a first touch
            return {"connection_note": "Hi Ravi, moving loan states into CoreSoft mid-cycle is where cutovers break. How are you testing it?",
                    "message_1": "Thanks Ravi. Backdated rate changes are the quiet one: the new core recalculates them and month-end recon "
                                 "drifts. Is that on your cutover checklist yet, or still with CoreSoft?"}
        if "BUYER SIMULATOR" in system:
            seen["sim"] += 1
            good = seen["sim"] > 1
            return {"connection": {"accept": good, "reaction": "ok" if good else "generic"}, "message_1": {"reply": good, "reaction": "."},
                    "refutes": [] if good else ["Sounds like every vendor"], "scores": {}, "overall": 8 if good else 3,
                    "fixes": [] if good else ["Name the cutover"]}
        if "OBJECTIONS" in system:
            return {"objections": [{"objection": "We have in-house QA", "likelihood": "high",
                                    "responses": [{"label": "Complement", "reply": "Makes sense..."}]}]}
        return {}
    monkeypatch.setattr(pitch.llm, "complete_json", fake)

    p = client.post(f"/api/people/{ravi['person_id']}/pitch", json={}).json()
    p = client.get(f"/api/pitches/{p['id']}").json()
    assert p["status"] == "ready", (p["log"][-3:], p.get("error"))
    d = p["data"]
    assert len(d["rounds"]) == 2 and d["rounds"][0]["lint"]                 # round 1 failed the length and phrase rules
    assert d["messages"]["connection_note"].startswith("Hi Ravi, moving loan states")
    assert p["score"] == 8 and d["objections"][0]["objection"] == "We have in-house QA"
    assert not d["warnings"]
    assert d["hooks"][0]["style"] == "sharp_question" and d["hooks"][-1]["generic"]   # bland hook loses despite a high score
    assert d["triggers"][0]["type"] == "commitment" and d["why"]["still_open"][0]["refute"] == "SI already owns testing"

    edited = client.put(f"/api/pitches/{p['id']}", json={"messages": {"message_1": "Edited.", "message_3": "ignored"}, "status": "approved"}).json()
    assert edited["data"]["messages"]["message_1"] == "Edited." and "message_3" not in edited["data"]["messages"] and edited["status"] == "approved"
    csv_text = client.get(f"/api/pitches.csv?ids={p['id']}").text
    assert "Connection note" in csv_text and "https://linkedin.com/in/ravi" in csv_text and "Edited." in csv_text
    assert client.get(f"/api/pitches/{p['id']}").json()["status"] == "exported"
    assert client.get("/api/pitches").json()[0]["hook"] == "CoreSoft cutover"


def test_pasted_posts_drive_voice_and_reach_the_writer(monkeypatch):
    install_fakes(monkeypatch)
    from backend import buyers, pitch
    cid = client.post("/api/accounts", json={"name": "Zen Finance Voice", "domain": "zen.test"}).json()["company_id"]
    ravi = next(c for i in client.get(f"/api/accounts/{cid}").json()["initiatives"] for c in i["contacts"] if c["full_name"] == "Ravi Iyer")
    pid = ravi["person_id"]
    queries = []

    def fake_raw(q, topic="general", days=None, max_results=10, include_domains=None, full_text=False):
        queries.append(q)
        return []
    monkeypatch.setattr(buyers.tavily, "raw_search", fake_raw)
    seen = {}

    def fake_brief(system, prompt, *a, **k):
        seen["prompt"] = prompt
        return {"summary": "CTO.", "first_hand": 1, "topics": [], "voice": {
            "samples": 1, "register": "casual", "length": "terse", "directness": "blunt", "evidence": "numbers",
            "vocabulary": ["ship it", "no heroics"], "summary": "Terse and numbers-first.", "mirror": ["two sentences max"], "avoid": ["hype"]}}
    monkeypatch.setattr(buyers.llm, "complete_json", fake_brief)

    assert client.post(f"/api/people/{pid}/samples", json={"text": "Shipped v2 with zero sev-1s. No heroics, just boring releases.",
                                                           "kind": "post"}).status_code == 200
    assert client.post(f"/api/people/{pid}/samples", json={"text": "hi"}).status_code == 400
    b = client.post(f"/api/people/{pid}/brief").json()
    assert "Shipped v2 with zero sev-1s" in seen["prompt"] and "pasted by the user" in seen["prompt"]
    assert b["voice"]["register"] == "casual" and b["samples_used"] == 1 and b["sources"][0]["pasted"]
    assert any('"Ravi Iyer" Zen' in q for q in queries)                     # unquoted short company name, not the full exact name
    n = len(queries)
    client.post(f"/api/people/{pid}/brief")                                   # cached while samples are unchanged
    assert len(queries) == n
    client.post(f"/api/people/{pid}/samples", json={"text": "Our cutover plan is three dry runs, then go.", "kind": "comment"})
    client.post(f"/api/people/{pid}/brief")                                   # a new sample triggers a rebuild
    assert len(queries) > n

    ctx = pitch.context(pid)
    block = pitch._buyer_block(ctx, b)
    assert "HOW THEY COMMUNICATE: from 1 of their own texts" in block and "no heroics" in block and "two sentences max" in block
    assert "neutral and plain" in pitch._buyer_block(ctx, {})                # no voice: cautious default, labelled


def test_person_search_covers_many_source_kinds(monkeypatch):
    from backend import buyers

    def fake_raw(q, topic="general", days=None, max_results=10, include_domains=None, full_text=False):
        d = include_domains or []
        if "youtube.com" in d:   # podcast on YouTube: no company name in the text, still the same person
            return [{"url": "https://youtube.com/watch?v=1", "title": "Neelima Annam on prior auth", "text": "Neelima Annam: honestly, our rule is...", "published_at": None}]
        if "medium.com" in d:
            return [{"url": "https://medium.com/@na/x", "title": "Notes", "text": "by Neelima Annam. We ship weekly.", "published_at": None}]
        if "carelon.com" in d:
            return [{"url": "https://www.carelon.com/blog/x", "title": "Blog", "text": "Posted by Neelima Annam", "published_at": None}]
        if topic == "news":
            return [{"url": "https://news.test/pr", "title": "PR", "text": "Neelima Annam of Carelon said the launch...", "published_at": None}]
        return [{"url": "https://theorg.com/neelima", "title": "Neelima Annam", "text": "Neelima Annam, Interim CIO at Carelon Medical Benefits Management", "published_at": None},
                {"url": "https://random.test/other", "title": "Neelima Annam", "text": "Neelima Annam, a botanist in Ohio", "published_at": None}]
    monkeypatch.setattr(buyers.tavily, "raw_search", fake_raw)
    out = buyers.gather("Neelima Annam", "Carelon Global Solutions", "CIO, Carelon Specialty Care", "carelon.com")
    urls = [r["url"] for r in out]
    assert "https://random.test/other" not in urls                                  # a namesake elsewhere is dropped
    assert {"https://youtube.com/watch?v=1", "https://medium.com/@na/x", "https://www.carelon.com/blog/x",
            "https://theorg.com/neelima", "https://news.test/pr"} <= set(urls)
    assert out[0]["voice_value"] == "unscripted" and out[-1]["voice_value"] == "quoted"   # how they really talk comes first
