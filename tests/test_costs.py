import json

from fastapi.testclient import TestClient

from backend import app as app_module, db, pitch

H = {"X-Requested-With": "accountscope"}


def _people(name):
    db.init()
    with db.session() as s:
        cid = s.execute("INSERT INTO company(workspace_id,name,domain) VALUES (1,?,'costco.example')", (name,)).lastrowid
        a = s.execute("INSERT INTO person(company_id,full_name,title) VALUES (?, 'Asha Rao', 'CIO')", (cid,)).lastrowid
        b = s.execute("INSERT INTO person(company_id,full_name,title,email) VALUES (?, 'Ben Lee', 'CTO', 'ben@costco.example')", (cid,)).lastrowid
        m = s.execute("INSERT INTO person(company_id,full_name,title) VALUES (?, 'Mira K***', 'VP QA')", (cid,)).lastrowid
    return cid, a, b, m


def test_cost_estimates():
    cid, a, b, m = _people('CostCo Global')
    c = TestClient(app_module.app)

    e = c.get(f"/api/people/{a}/cost?action=enrich", headers=H).json()
    assert e["lines"][0]["service"] == "Apollo" and e["lines"][0]["amount"] == "1 credit"
    assert c.get(f"/api/people/{b}/cost?action=enrich", headers=H).json()["free"] is True   # already has email

    br = c.get(f"/api/people/{a}/cost?action=brief", headers=H).json()
    tav = next(l for l in br["lines"] if l["service"] == "Tavily")
    assert "credits" in tav["amount"] and int(tav["amount"].split()[2]) >= 12   # 6+ advanced searches x 2

    p = c.get(f"/api/people/{a}/cost?action=pitch", headers=H).json()
    ai = next(l for l in p["lines"] if "AI calls" in l["amount"])
    lo, hi = [int(x) for x in ai["amount"].split()[0].split("–")]
    assert lo == 1 + 6 + 2 and hi == 1 + 6 + 2 * pitch.MAX_ROUNDS

    # a saved, fresh brief means no search credits
    with db.session() as s:
        s.execute("INSERT INTO buyer_brief(person_id, brief, sources) VALUES (?,?,?)", (a, json.dumps({"summary": "x", "samples_used": 0}), "[]"))
    p2 = c.get(f"/api/people/{a}/cost?action=pitch", headers=H).json()
    assert not any(l["service"] == "Tavily" for l in p2["lines"]) and any("Reuses" in n for n in p2["notes"])

    masked = c.get(f"/api/people/{m}/cost?action=pitch", headers=H).json()
    assert any("surname hidden" in n for n in masked["notes"])
    assert c.get(f"/api/people/{a}/cost?action=nope", headers=H).status_code == 400


def test_pitch_list_has_email():
    cid, a, b, m = _people('CostCo Two')
    pid = pitch.create(b)
    rows = pitch.list_all(cid, 1)
    assert any(r["id"] == pid and r["email"] == "ben@costco.example" for r in rows)
