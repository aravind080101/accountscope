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
    brief = {"openers": [{"level": "L3", "text": "Left RBL to lead a bank founded in 1904", "source": 0}]}
    note = "Hi Vijay, going from RBL to a bank founded in 1904 is a rare move. What drew you to it?"
    ok = {"connection_note": note,
          "message_1": "Moving customers to new net banking is where payees go missing. At Moolya we test migrations like this "
                       "on real accounts before cutover. Happy to do 15 minutes if useful?"}
    assert pitch.lint(ok, None, "Moolya", brief, profile) == []          # one plain 'who we are' + a soft open door is fine
    bad = {"connection_note": "Hi Vijay, quick note about QA.",
           "message_1": "Moolya's Migration Assurance is trusted by 50,000+ engineers. Moolya can help. Can we book a call Tuesday?"}
    issues = " | ".join(pitch.lint(bad, None, "Moolya", brief, profile))
    assert "no personal hook" in issues
    assert "at most once" in issues and "Migration Assurance" in issues and "stat" in issues and "asks for time" in issues


def test_message_2_and_full_pitch_rules():
    good = {"message_2": "One thing I keep seeing on Smart TV launches: DRM licences renew fine on phones but fail on older "
                         "Tizen models. One idea: a 2-day pass on your top 5 TV models before the next release. "
                         "Worth 15 minutes next week to walk through it?",
            "full_pitch": "Glad that landed. We are a testing team that works on streaming apps, mostly playback and devices. "
                          "For your Smart TV rollout we would map your top devices, run DRM and playback checks on real TVs, "
                          "then automate the ones that break most. Happy to share the device checklist. "
                          "Would 15 minutes on Thursday work?"}
    assert pitch.lint_sequence(good, "Moolya") == []
    bad = dict(good, message_2="Just checking in on my last note.",
               full_pitch="- point one\n- point two")
    issues = " | ".join(pitch.lint_sequence(bad, "Moolya"))
    assert "just checking" in issues and "15-minute ask" in issues and "bullet" in issues and "who we are" in issues


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


def test_same_person_written_differently_is_one_record():
    from backend import people, db
    assert people.name_key("Dr N Kamakodi") == people.name_key("Dr. N. Kamakodi") == people.name_key("N Kamakodi")
    assert people.name_key("R. Vijay Anandh") == people.name_key("Vijay Anandh R") == people.name_key("Vijay Anandh")
    assert people.name_key("A Kumar") != people.name_key("B Kumar")
    assert people.name_key("Ravi I***") is None
    with db.session() as s:
        cid = s.execute("INSERT INTO company(name) VALUES ('Dupe Bank')").lastrowid
        a = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'R. Vijay Anandh', 'MD & CEO')", (cid,)).lastrowid
        b = s.execute("INSERT INTO person(company_id, full_name, title, email) VALUES (?, 'Vijay Anandh R', 'Managing Director', 'v@x.test')",
                      (cid,)).lastrowid
        c = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Dr N Kamakodi', 'MD & CEO')", (cid,)).lastrowid
        s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Dr. N. Kamakodi', 'MD & CEO (upto April 30, 2026)')", (cid,))
        s.execute("INSERT INTO buyer_brief(person_id, brief, sources) VALUES (?, '{}', '[]')", (a,))
        assert people.canonical_name(s, cid, "Dr. N Kamakodi") == "Dr N Kamakodi"
    assert people.merge_duplicates(cid) == 2
    with db.session() as s:
        rows = {r["full_name"]: dict(r) for r in s.execute("SELECT * FROM person WHERE company_id=?", (cid,))}
        assert len(rows) == 2
        vijay = rows["Vijay Anandh R"]                       # the one with an email is kept
        assert vijay["id"] == b and s.execute("SELECT 1 FROM buyer_brief WHERE person_id=?", (b,)).fetchone()   # brief moved over
        assert "upto" in next(r["title"] for n, r in rows.items() if "Kamakodi" in n)               # former role stays visible


def test_interests_can_come_from_any_cited_page_but_traits_need_their_words():
    sources = [{"url": "a", "voice_value": "bio"}, {"url": "b", "voice_value": "written"}]
    raw = {"traits": {}, "values": [{"text": "mentoring", "source": 0}],                       # bio only: not their words
           "interests": [{"text": "Runs the Chennai marathon", "source": 0},                  # bio is fine for an interest
                         {"text": "Weekends with his family", "source": 0},                    # private: dropped
                         {"text": "Chess", "source": 7}]}                                       # no such source
    p = buyers._clean_personality(raw, sources)
    assert [x["text"] for x in p["interests"]] == ["Runs the Chennai marathon"]
    assert p["values"] == []


def test_deck_passages_only_when_they_match_the_need():
    from backend import profiles, db
    with db.session() as s:
        s.execute("DELETE FROM seller_doc")
        s.execute("INSERT INTO seller_doc(workspace_id, name, kind, text) VALUES (1, 'Banking deck', 'deck', ?)",
                  ("Core banking migration testing: we reconcile standing instructions, beneficiaries and transaction limits "
                   "per customer before cutover, and inject timeouts after each migration step. " * 3,))
        s.execute("INSERT INTO seller_doc(workspace_id, name, kind, text) VALUES (1, 'OTT deck', 'deck', ?)",
                  ("Streaming apps: we test playback across smart TVs, DRM licences and adaptive bitrate on low bandwidth. " * 3,))
        s.execute("INSERT INTO seller_doc(workspace_id, name, kind, text) VALUES (1, 'CEO post', 'pov', ?)",
                  ("Core banking migration standing instructions beneficiaries cutover. " * 5,))
    got = profiles.relevant_material("New net banking platform, core banking migration, cutover of standing instructions and beneficiaries")
    assert got and got[0]["doc"] == "Banking deck" and all(m["doc"] != "CEO post" for m in got)   # POV material isn't offerings
    assert all(m["doc"] != "OTT deck" for m in got)
    assert profiles.relevant_material("hospital patient scheduling for clinics") == []           # nothing fits: nothing used


def test_former_ceo_is_marked_and_kept_out_of_the_chart():
    from datetime import date
    from backend import people, db, orgchart
    T = date(2026, 11, 16)
    assert people.role_status("Managing Director & CEO (upto April 30, 2026)", T)[0] is False
    assert people.role_status("MD & CEO (w.e.f. May 1, 2026)", T)[0] is True
    assert people.role_status("CEO w.e.f. 01.01.2027", T)[0] is False          # not started yet
    assert people.role_status("Chief Business Officer", T) == (None, None)
    with db.session() as s:
        cid = s.execute("INSERT INTO company(name) VALUES ('Succession Bank')").lastrowid
        old = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Dr N Kamakodi', 'MD & CEO')", (cid,)).lastrowid
        new = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'R. Vijay Anandh', 'MD & CEO (w.e.f. May 1, 2026)')",
                        (cid,)).lastrowid
        s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Kamal Sabhlok', 'Chief Business Officer')", (cid,))
    assert people.refresh_status(cid, T) == 1
    with db.session() as s:
        r = s.execute("SELECT current, left_note FROM person WHERE id=?", (old,)).fetchone()
        assert r["current"] == 0 and "Succeeded by R. Vijay Anandh" in r["left_note"]
        assert s.execute("SELECT current FROM person WHERE id=?", (new,)).fetchone()["current"] != 0
    o = orgchart.build(cid)
    assert {n["name"] for n in o["nodes"]} == {"R. Vijay Anandh", "Kamal Sabhlok"}
    assert [f["name"] for f in o["former"]] == ["Dr N Kamakodi"]


def test_leadership_check_retires_people_recent_sources_say_have_left(monkeypatch):
    from backend import people, db, config, llm
    from backend.providers import tavily
    with db.session() as s:
        cid = s.execute("INSERT INTO company(name, domain) VALUES ('Any Corp', 'anycorp.test')").lastrowid
        old = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Asha Rao', 'Chief Executive Officer')", (cid,)).lastrowid
        new = s.execute("INSERT INTO person(company_id, full_name, title) VALUES (?, 'Ben Kurian', 'CEO')", (cid,)).lastrowid
    monkeypatch.setattr(config, "TAVILY_API_KEY", "x")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(tavily, "raw_search", lambda q, **k: [{"url": "https://news.test/ceo", "title": "Ben Kurian takes charge",
                                                               "published_at": "2026-07-01", "text": "Ben Kurian succeeded Asha Rao as CEO on 1 July 2026."}])
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {
        "current": [{"role": "CEO", "name": "Ben Kurian", "since": "2026-07-01", "source": 0}],
        "former": [{"name": "Asha Rao", "role": "CEO", "reason": "Succeeded by Ben Kurian on 1 July 2026", "source": 0},
                   {"name": "Ben Kurian", "role": "CEO", "reason": "contradiction", "source": 0}]})   # contradictions are ignored
    res = people.verify_leadership({"id": cid, "name": "Any Corp", "domain": "anycorp.test"})
    people.refresh_status(cid)                      # title rules must not undo the check
    with db.session() as s:
        a = s.execute("SELECT current, left_note FROM person WHERE id=?", (old,)).fetchone()
        b = s.execute("SELECT current FROM person WHERE id=?", (new,)).fetchone()
    assert res["changed"] == 1 and a["current"] == 0 and "Succeeded by Ben Kurian" in a["left_note"] and b["current"] != 0


def test_conversation_must_lead_to_a_named_use_case():
    profile = {"offerings": [{"name": "Migration testing"}]}
    seq = {"message_2": "One idea for the net banking migration: reconcile payees per customer. Worth 15 minutes next week?",
           "full_pitch": "We test migrations. For your net banking migration we would reconcile every customer. 15 minutes Thursday?"}
    goal = {"offering": "Migration testing", "use_case": "Testing the net banking migration of beneficiaries and limits"}
    assert pitch.lint_goal(goal, seq, profile) == []
    assert "END GOAL" in pitch.lint_goal({}, seq, profile)[0]
    assert any("not one of the seller's offerings" in i for i in pitch.lint_goal({**goal, "offering": "Game testing"}, seq, profile))
    vague = dict(seq, full_pitch="We help teams. 15 minutes Thursday?")
    assert any("Full pitch" in i for i in pitch.lint_goal(goal, vague, profile))