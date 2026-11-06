
from fastapi.testclient import TestClient


def test_proxy_only_blocks_direct_requests(monkeypatch):
    from backend import app as app_module, config
    monkeypatch.setattr(config, "PROXY_ONLY", True)
    monkeypatch.setattr(config, "INTERNAL_TOKEN", "tok123")
    c = TestClient(app_module.app)
    assert c.get("/health").status_code == 200                       # Render's health check stays open
    r = c.get("/api/auth/status", headers={"X-Requested-With": "accountscope"})
    assert r.status_code == 403 and "workers.dev" in r.text
    r = c.get("/api/auth/status", headers={"X-Requested-With": "accountscope", "x-proxy-token": "wrong"})
    assert r.status_code == 403
    r = c.get("/api/auth/status", headers={"X-Requested-With": "accountscope", "x-proxy-token": "tok123"})
    assert r.status_code == 200


def test_proxy_only_off_by_default():
    from backend import app as app_module, config
    assert config.PROXY_ONLY is False
    assert TestClient(app_module.app).get("/api/auth/status", headers={"X-Requested-With": "accountscope"}).status_code == 200


def test_keys_never_reach_the_browser(monkeypatch):
    from backend import app as app_module, config, db
    key = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefgh"
    monkeypatch.setattr(config, "OPENAI_API_KEY", key)
    db.init()
    with db.session() as s:
        cid = s.execute("INSERT INTO company(workspace_id,name) VALUES (1,'Leaky Bank')").lastrowid
        s.execute("INSERT INTO run(company_id,status,error,log) VALUES (?, 'failed', ?, '[]')",
                  (cid, f"LocalProtocolError: Illegal header value b'Bearer \\n{key}'"))
    c = TestClient(app_module.app)
    body = c.get(f"/api/accounts/{cid}", headers={"X-Requested-With": "accountscope"}).text
    assert key not in body and "sk-proj-ABCDEF" not in body



def test_keys_are_trimmed():
    import subprocess, sys
    out = subprocess.run([sys.executable, "-c", "from backend import config; print(repr(config.OPENAI_API_KEY))"],
                         env={**__import__("os").environ, "OPENAI_API_KEY": "\n sk-test-123 \n"},
                         capture_output=True, text=True).stdout.strip()
    assert out == "'sk-test-123'"
