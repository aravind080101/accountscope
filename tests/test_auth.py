"""Sign-in, roles, and the wall between client workspaces."""
from fastapi.testclient import TestClient

from backend import app as app_module, auth, config, db, profiles, tenancy

H = {"X-Requested-With": "accountscope"}


def _client():
    return TestClient(app_module.app, headers=H)


def _login(c, email, pw):
    return c.post("/api/auth/login", json={"email": email, "password": pw})


def test_login_roles_and_workspace_isolation(monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_LOGIN", True)
    monkeypatch.setattr(config, "ALLOW_SETUP", True)
    auth._cache.clear()
    auth._attempts.clear()
    with db.session() as s:  # data from other test files lives in workspace 1
        s.execute("DELETE FROM auth_session")
        s.execute("DELETE FROM app_user")
        s.execute("INSERT OR IGNORE INTO company(workspace_id, name) VALUES (1, 'Moolya Client One')")
        ws1_company = s.execute("SELECT id FROM company WHERE workspace_id=1 LIMIT 1").fetchone()["id"]
        s.execute("INSERT OR IGNORE INTO person(company_id, full_name, title) VALUES (?, 'Private Person', 'CTO')", (ws1_company,))
        ws1_person = s.execute("SELECT id FROM person WHERE company_id=? LIMIT 1", (ws1_company,)).fetchone()["id"]

    anon = _client()
    assert anon.get("/api/auth/status").json()["needs_setup"] is True
    assert anon.get("/api/accounts").status_code == 401
    assert TestClient(app_module.app).post("/api/auth/login", json={"email": "x", "password": "y"}).status_code == 403  # no app header

    # first visitor becomes the platform owner (local setup only)
    owner = _client()
    assert owner.post("/api/auth/setup", json={"email": "Owner@Moolya.com", "password": "weak"}).status_code == 400
    r = owner.post("/api/auth/setup", json={"email": "Owner@Moolya.com", "name": "Aravind", "password": "Str0ngPassw0rd", "company": "Moolya"})
    assert r.status_code == 200
    assert anon.post("/api/auth/setup", json={"email": "evil@x.com", "password": "Str0ngPassw0rd"}).status_code == 404  # only once
    me = owner.get("/api/auth/me").json()
    assert me["user"]["is_superadmin"] and me["workspace"]["id"] == 1
    assert owner.get("/api/accounts").status_code == 200 and any(a["id"] == ws1_company for a in owner.get("/api/accounts").json())

    # owner creates a client workspace with its admin
    created = owner.post("/api/workspaces", json={"name": "Acme Testing", "admin_email": "lead@acme.test", "admin_name": "Lea"}).json()
    acme_id, temp = created["workspace"]["id"], created["temp_password"]

    acme = _client()
    assert _login(acme, "lead@acme.test", "nope").status_code == 401
    assert _login(acme, "LEAD@acme.test", temp).json()["must_change_password"] is True
    assert acme.get("/api/accounts").status_code == 403                    # must change the temporary password first
    assert acme.post("/api/auth/password", json={"current": temp, "new": "short"}).status_code == 400
    assert acme.post("/api/auth/password", json={"current": temp, "new": "AcmeLead2026x"}).status_code == 200

    # the wall: Acme sees nothing of workspace 1, and every id-based route answers 404
    assert acme.get("/api/accounts").json() == []
    assert acme.get(f"/api/accounts/{ws1_company}").status_code == 404
    assert acme.get(f"/api/accounts/{ws1_company}/org").status_code == 404
    assert acme.post(f"/api/accounts/{ws1_company}/watch", json={"watch": True}).status_code == 404
    assert acme.delete(f"/api/accounts/{ws1_company}").status_code == 404
    assert acme.get(f"/api/people/{ws1_person}/brief").status_code == 404
    assert acme.post(f"/api/people/{ws1_person}/enrich").status_code == 404
    assert acme.post(f"/api/people/{ws1_person}/samples", json={"text": "a long enough sample of text"}).status_code == 404
    assert acme.get("/api/pitches").json() == []
    assert acme.get("/api/alerts").json()["unread"] == 0
    assert acme.get("/api/summary").json()["totals"]["accounts"] == 0
    assert acme.post("/api/workspaces", json={"name": "x", "admin_email": "a@b.co"}).status_code == 403
    assert acme.post("/api/auth/switch", json={"workspace_id": 1}).status_code == 403

    # each workspace has its own seller profile
    assert acme.get("/api/profile").json()["profile"]["company"] == "Acme Testing"
    acme.put("/api/profile", json={**profiles.blank("Acme Testing"), "offerings": [{"name": "Load testing"}]})
    assert owner.get("/api/profile").json()["profile"]["company"] != "Acme Testing"

    # an account Acme adds is invisible to workspace 1, and the same name can exist in both
    with db.session() as s:
        acme_co = s.execute("INSERT INTO company(workspace_id, name) VALUES (?, 'Moolya Client One')", (acme_id,)).lastrowid
    assert [a["id"] for a in acme.get("/api/accounts").json()] == [acme_co]
    assert owner.get(f"/api/accounts/{acme_co}").status_code == 404
    assert owner.post("/api/auth/switch", json={"workspace_id": acme_id}).status_code == 200   # the owner can step in
    assert owner.get(f"/api/accounts/{acme_co}").status_code == 200
    owner.post("/api/auth/switch", json={"workspace_id": 1})

    # team management inside Acme
    added = acme.post("/api/team", json={"email": "rep@acme.test", "name": "Rep"}).json()
    rep = _client()
    _login(rep, "rep@acme.test", added["temp_password"])
    rep.post("/api/auth/password", json={"current": added["temp_password"], "new": "RepAcme2026xx"})
    assert rep.get("/api/accounts").status_code == 200
    assert rep.get("/api/team").status_code == 403                           # members can't manage the team
    assert acme.post("/api/team", json={"email": "rep@acme.test"}).status_code == 400
    assert acme.post("/api/team", json={"email": "owner@moolya.com"}).status_code == 400
    owner_id = owner.get("/api/auth/me").json()["user"]["id"]
    assert acme.post(f"/api/team/{owner_id}/reset").status_code == 404      # can't touch users outside the workspace
    acme.patch(f"/api/team/{added['user']['id']}", json={"active": False})
    auth._cache.clear()
    assert rep.get("/api/accounts").status_code == 401                       # deactivated: signed out everywhere

    # brute force is slowed down
    auth._attempts.clear()
    bad = _client()
    codes = [_login(bad, "lead@acme.test", f"wrong{i}").status_code for i in range(9)]
    assert codes[:8] == [401] * 8 and codes[8] == 429

    assert owner.post("/api/auth/logout").status_code == 200
    assert owner.get("/api/accounts").status_code == 401


def test_owner_recovery_from_secrets(monkeypatch):
    with db.session() as s:
        s.execute("DELETE FROM auth_session")
        s.execute("DELETE FROM app_user")
        s.execute("INSERT INTO app_user(workspace_id, email, password_hash, role) VALUES (2, 'someone@client.test', 'x', 'admin')")
    monkeypatch.setattr(config, "ADMIN_EMAIL", "owner@moolya.test")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "FirstPassw0rd")
    auth.bootstrap()                                              # other users exist: the owner is still created
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "RecoveredPassw0rd")
    auth.bootstrap()                                              # an active owner exists: nothing changes
    with db.session() as s:
        h = s.execute("SELECT password_hash FROM app_user WHERE email='owner@moolya.test'").fetchone()["password_hash"]
        assert auth.verify_password("FirstPassw0rd", h)
        s.execute("UPDATE app_user SET active=0 WHERE is_superadmin=1")   # the documented recovery step
    auth.bootstrap()
    with db.session() as s:
        r = s.execute("SELECT * FROM app_user WHERE email='owner@moolya.test'").fetchone()
        assert r["active"] == 1 and r["is_superadmin"] == 1 and auth.verify_password("RecoveredPassw0rd", r["password_hash"])
        s.execute("DELETE FROM app_user")
