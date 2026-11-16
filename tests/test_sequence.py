"""Person-first openers, no early selling, stages 3-9 rules, offering ranking."""
from backend import buyers, pitch


def test_openers_need_a_source_and_skip_private_topics():
    raw = [{"level": "L3", "text": "Left RBL to lead a bank founded in 1904", "source": 0},
           {"level": "L1", "text": "Runs the Chennai marathon every year", "source": 1},
           {"level": "L1", "text": "Spends weekends with his family", "source": 1},     # private
           {"level": "L2", "text": "Said trust beats speed", "source": 9},              # source doesn't exist
           {"level": "L9", "text": "Not a level", "source": 0}]
    out = buyers.clean_openers(raw, n_sources=2)
    assert [o["level"] for o in out] == ["L1", "L3"]
    assert "family" not in " ".join(o["text"] for o in out)


def test_first_two_messages_cannot_sell():
    profile = {"company": "Moolya", "offerings": [{"name": "Migration Assurance"}]}
    msgs = {"connection_note": "Hi Vijay, going from RBL to a bank founded in 1904 is a rare move. What drew you to it?",
            "message_1": "Moolya's Migration Assurance is trusted by 50,000+ engineers across 25 countries. Thoughts?"}
    issues = " | ".join(pitch.lint(msgs, None, "Moolya", None, profile))
    assert "Don't name Moolya in Message 1" in issues
    assert "Migration Assurance" in issues
    assert "stat" in issues


def test_stages_3_to_9_rules():
    good = {"mirror": "That makes sense. Which product line worries you most?",
            "advice": "What would you do differently this time?",
            "give": "One pattern I keep seeing: totals match, per-customer checks don't.",
            "reveal": "I work on testing at Moolya. How are you splitting the tests?",
            "interest_check": "Worth comparing notes on the cutover?",
            "contact": "I have a one-page checklist. Best email to send it to?",
            "specific_ask": "Would 15 minutes on Thursday at 4pm work?"}
    assert pitch.lint_sequence(good, "Moolya") == []
    bad = dict(good, mirror="Moolya can help, can we get on a call?", contact="Want the checklist?")
    issues = " | ".join(pitch.lint_sequence(bad, "Moolya"))
    assert "before stage 6" in issues and "asks for time" in issues and "email" in issues


def test_person_signals_count_as_specific():
    ctx = {"tech": [], "works": [], "vendors": [], "person": {"company": "City Union Bank"}}
    brief = {"openers": [{"level": "L1", "text": "Runs the Chennai marathon", "source": 0}]}
    assert pitch.bland_line("Hi Vijay, how does marathon training shape how you run a bank?", ctx, brief) is None
    assert pitch.bland_line("Hi Vijay, quality matters more than ever.", ctx, brief)


def test_offering_rank_weights(monkeypatch):
    from backend import profiles, db
    with db.session() as s:
        cid = s.execute("INSERT INTO company(name, industry) VALUES ('Rank Bank', 'Banking')").lastrowid
    monkeypatch.setattr(profiles, "load", lambda wid=None: {"offerings": [{"name": "Migration testing"}, {"name": "Game testing"}]})
    monkeypatch.setattr(profiles.llm, "complete_json", lambda *a, **k: {"rank": [
        {"offering": "Migration testing", "initiative_match": 1, "industry_match": 1, "proof_match": 1, "timing": 1, "size_fit": 1, "blockers": 0},
        {"offering": "Game testing", "initiative_match": 0.1, "industry_match": 0, "proof_match": 0, "timing": 0, "size_fit": 1, "blockers": 0.5},
        {"offering": "Invented offering", "initiative_match": 1}]})
    ranked = profiles.rank_offerings(cid, refresh=True)
    assert [r["offering"] for r in ranked] == ["Migration testing", "Game testing"]
    assert ranked[0]["score"] == 90 and ranked[0]["label"] == "lead"
    assert ranked[1]["label"] == "don't pitch"


def test_rerun_replaces_the_pitch_for_the_same_person(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app as appmod, db
    with db.session() as s:
        cid = s.execute("INSERT INTO company(name) VALUES ('Rerun Co')").lastrowid
        pid = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Asha Rao', 'CTO')", (cid,)).lastrowid
    old = pitch.create(pid)
    with db.session() as s:
        s.execute("UPDATE pitch SET status='approved' WHERE id=?", (old,))
    ran = []
    monkeypatch.setattr(pitch, "run_queue", lambda ids: ran.extend(ids))
    monkeypatch.setattr(appmod.llm, "available", lambda: True)
    c = TestClient(appmod.app, headers={"X-Requested-With": "accountscope"})
    r = c.post("/api/pitches/rerun", json={"ids": [old]})
    assert r.status_code == 200, r.text
    new_ids = r.json()["pitch_ids"]
    assert len(new_ids) == 1 and ran == new_ids
    with db.session() as s:
        assert s.execute("SELECT COUNT(*) n FROM pitch WHERE person_id=?", (pid,)).fetchone()["n"] == 1   # old one replaced, even if approved
        assert s.execute("SELECT person_id, status FROM pitch WHERE id=?", (new_ids[0],)).fetchone()["status"] == "queued"
    assert c.get(f"/api/pitches/rerun/cost?ids={new_ids[0]}").status_code == 200
