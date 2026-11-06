
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
