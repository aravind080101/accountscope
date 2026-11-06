"""The app on Cloudflare D1: same flows, through the Worker's /query contract (simulated over HTTP)."""
import os
import re
import sqlite3
import tempfile

import httpx

from backend import db


def _fake_worker(path):
    """Mirrors cloudflare/worker.ts: run each statement against the database; reads return columns + rows."""
    conn = sqlite3.connect(path, check_same_thread=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "d1.internal" and request.url.path == "/query"
        out = []
        try:
            for st in httpx.Response(200, content=request.content).json()["statements"]:
                cur = conn.execute(st["sql"], st["params"])
                if re.match(r"\s*(select|pragma|with)", st["sql"], re.I):
                    out.append({"columns": [d[0] for d in cur.description or []], "rows": [list(r) for r in cur.fetchall()]})
                else:
                    out.append({"columns": [], "rows": [], "last_row_id": cur.lastrowid, "changes": cur.rowcount})
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            return httpx.Response(200, json={"error": str(exc)})
        return httpx.Response(200, json={"results": out})
    return handler


def test_full_research_flow_on_d1(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(), "d1.db")
    monkeypatch.setattr(db, "D1_PROXY_URL", "http://d1.internal")
    client = httpx.Client(transport=httpx.MockTransport(_fake_worker(path)))
    monkeypatch.setattr(db, "_client", lambda: client)
    db.init()
    db.init()  # idempotent on restart

    with db.session() as s:
        assert s.execute("SELECT name FROM workspace WHERE id=1").fetchone()["name"]
        cid = s.execute("INSERT INTO company(workspace_id, name) VALUES (1, 'D1 Co')").lastrowid
        row = s.execute("SELECT * FROM company WHERE id=?", (cid,)).fetchone()
        assert row["name"] == "D1 Co" and row[2] == "D1 Co" and dict(row)["workspace_id"] == 1
        s.executemany("INSERT INTO cache(key, value) VALUES (?, ?)", [("a", "1"), ("b", "2")])
        assert [r["key"] for r in s.execute("SELECT key FROM cache ORDER BY key")] == ["a", "b"]
        assert s.execute("SELECT * FROM company WHERE id=-1").fetchone() is None
        try:
            s.execute("INSERT INTO company(workspace_id, name) VALUES (1, 'D1 Co')")
            raise AssertionError("expected a constraint error")
        except sqlite3.IntegrityError:
            pass

    # the whole research pipeline and the API, end to end, on the D1 path
    from fastapi.testclient import TestClient
    from backend import app as app_module
    from tests.test_features import install_fakes
    install_fakes(monkeypatch)
    api = TestClient(app_module.app, headers={"X-Requested-With": "accountscope"})
    new = api.post("/api/accounts", json={"name": "Zen Finance D1", "domain": "zen.test"}).json()["company_id"]
    d = api.get(f"/api/accounts/{new}").json()
    assert d["run"]["status"] == "done", d["run"]
    assert d["initiatives"] and d["initiatives"][0]["contacts"]
    assert api.get(f"/api/accounts/{new}/org").json()["nodes"]
    assert api.get("/api/accounts").json()[0]["name"] == "Zen Finance D1"
