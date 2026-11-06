"""Storage. SQLite on your own machine; Cloudflare D1 when deployed (set D1_PROXY_URL).

Both speak the same SQL dialect (D1 is SQLite), so the rest of the app uses one interface:
`with session() as s: s.execute(sql, params)`. On Cloudflare the container sends each statement to
an outbound handler in the Worker (http://d1.internal), which runs it against the D1 binding.
"""
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx

from . import config

D1_PROXY_URL = os.getenv("D1_PROXY_URL", "").rstrip("/")

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    profile TEXT,                               -- JSON: what this workspace sells
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_user (
    id INTEGER PRIMARY KEY,
    workspace_id INTEGER REFERENCES workspace(id),
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',        -- admin | member (of their workspace)
    is_superadmin INTEGER DEFAULT 0,            -- platform owner: creates workspaces
    must_change_password INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS auth_session (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_user(id),
    workspace_id INTEGER,                       -- the workspace this session is looking at
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS company (
    id INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    domain TEXT,
    industry TEXT,
    hq_country TEXT,
    summary TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, name)
);
CREATE TABLE IF NOT EXISTS run (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(id),
    status TEXT NOT NULL DEFAULT 'queued',      -- queued | running | done | failed
    mode TEXT,
    log TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS document (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(id),
    source_type TEXT,                           -- news | jobs | filing | blog | other
    url TEXT,
    title TEXT,
    published_at TEXT,
    text TEXT,
    UNIQUE(company_id, url)
);
CREATE TABLE IF NOT EXISTS initiative (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(id),
    name TEXT NOT NULL,
    category TEXT,
    stage TEXT,
    summary TEXT,
    tech TEXT DEFAULT '[]',
    first_seen TEXT,
    last_seen TEXT,
    confidence REAL,
    fit_score REAL,
    fit_reason TEXT
);
CREATE TABLE IF NOT EXISTS initiative_evidence (
    initiative_id INTEGER NOT NULL REFERENCES initiative(id),
    document_id INTEGER NOT NULL REFERENCES document(id),
    quote TEXT,
    PRIMARY KEY (initiative_id, document_id)
);
CREATE TABLE IF NOT EXISTS person (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(id),
    full_name TEXT NOT NULL,
    title TEXT,
    seniority TEXT,
    linkedin_url TEXT,
    apollo_id TEXT,
    email TEXT,
    phone TEXT,
    source TEXT,                                -- evidence | apollo
    UNIQUE(company_id, full_name)
);
CREATE TABLE IF NOT EXISTS vendor (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(id),
    name TEXT NOT NULL,
    relationship TEXT,                          -- selected | partner | incumbent | replacing | evaluating
    area TEXT,
    quote TEXT,
    document_id INTEGER REFERENCES document(id),
    is_competitor INTEGER DEFAULT 0,
    UNIQUE(company_id, name, area)
);
CREATE TABLE IF NOT EXISTS tech (
    company_id INTEGER NOT NULL REFERENCES company(id),
    name TEXT NOT NULL,
    category TEXT,
    source TEXT,                                -- builtwith | jobs | news | blog | filing
    document_id INTEGER,
    seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id, name)
);
CREATE TABLE IF NOT EXISTS location (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(id),
    city TEXT,
    country TEXT,
    type TEXT,                                  -- hq | office | rd_centre | engineering_centre | gcc | delivery_centre | plant | other
    functions TEXT DEFAULT '[]',                -- e.g. ["engineering","QA","data"]
    headcount INTEGER,
    quote TEXT,
    document_id INTEGER REFERENCES document(id),
    UNIQUE(company_id, city, country, type)
);
CREATE TABLE IF NOT EXISTS job_location (
    company_id INTEGER NOT NULL REFERENCES company(id),
    city TEXT NOT NULL,
    country TEXT,
    roles INTEGER DEFAULT 0,
    functions TEXT DEFAULT '[]',
    PRIMARY KEY (company_id, city)
);
CREATE TABLE IF NOT EXISTS project (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(id),
    name TEXT NOT NULL,
    counterparty TEXT NOT NULL,                 -- the client (or partner) on the other side
    direction TEXT,                             -- client: company delivers it | partner: counterparty delivers it
    status TEXT,                                -- announced | won | in_progress | live | completed
    summary TEXT,
    tech TEXT DEFAULT '[]',
    value TEXT,
    start_date TEXT,
    duration TEXT,
    counterparty_people TEXT DEFAULT '[]',      -- JSON [{name, title}] named on the client side
    owner_titles TEXT DEFAULT '[]',
    first_seen TEXT,
    last_seen TEXT,
    fit_score REAL,
    fit_reason TEXT,
    feedback TEXT,                              -- confirmed | dismissed
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS project_evidence (
    project_id INTEGER NOT NULL REFERENCES project(id),
    document_id INTEGER NOT NULL REFERENCES document(id),
    quote TEXT,
    PRIMARY KEY (project_id, document_id)
);
CREATE TABLE IF NOT EXISTS project_contact (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id),
    person_id INTEGER NOT NULL REFERENCES person(id),
    role TEXT,                                  -- Runs it | Sponsor | Team
    score REAL,
    rationale TEXT,
    source TEXT,                                -- evidence | apollo
    feedback TEXT,
    UNIQUE(project_id, person_id)
);
CREATE TABLE IF NOT EXISTS pitch (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES person(id),
    context_kind TEXT,                          -- initiative | project (optional focus)
    context_id INTEGER,
    status TEXT,                                -- queued | running | ready | approved | exported | failed
    score REAL,
    data TEXT,                                  -- JSON: angle, messages, rounds, simulation, objections
    log TEXT DEFAULT '[]',
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS person_sample (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES person(id),
    kind TEXT,                                  -- post | comment | reply | article | talk | other
    text TEXT NOT NULL,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS seller_doc (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,                         -- deck | web
    url TEXT,
    text TEXT NOT NULL,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS buyer_brief (
    person_id INTEGER PRIMARY KEY REFERENCES person(id),
    brief TEXT NOT NULL,                        -- JSON
    sources INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS alert (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES company(id),
    kind TEXT NOT NULL,                         -- new_initiative | stage_change | new_leader | hiring_surge | new_vendor
    title TEXT NOT NULL,
    detail TEXT,
    url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    read INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    target TEXT NOT NULL,                       -- contact | initiative
    person_name TEXT,
    title TEXT,
    initiative_name TEXT,
    category TEXT,
    verdict TEXT NOT NULL,                      -- confirmed | rejected | dismissed
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS title_stats (
    workspace_id INTEGER NOT NULL DEFAULT 1,
    category TEXT NOT NULL,
    title_key TEXT NOT NULL,
    confirms INTEGER DEFAULT 0,
    rejects INTEGER DEFAULT 0,
    PRIMARY KEY (workspace_id, category, title_key)
);
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS initiative_contact (
    id INTEGER PRIMARY KEY,
    initiative_id INTEGER NOT NULL REFERENCES initiative(id),
    person_id INTEGER NOT NULL REFERENCES person(id),
    role TEXT,                                  -- Owner | Sponsor | Influencer | Practitioner
    score REAL,
    rationale TEXT,
    opener TEXT,
    source TEXT,                                -- evidence | apollo (for THIS initiative)
    UNIQUE(initiative_id, person_id)
);
"""


def _connect() -> sqlite3.Connection:
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ------------------------------------------------------------------ D1 (Cloudflare)


class D1Row:
    """Behaves like sqlite3.Row: r["col"], r[0], dict(r), r.keys()."""
    __slots__ = ("_cols", "_vals")

    def __init__(self, cols: list[str], vals: list):
        self._cols, self._vals = cols, vals

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        try:
            return self._vals[self._cols.index(k)]
        except ValueError:
            raise IndexError(f"No such column: {k}") from None

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


class D1Cursor:
    def __init__(self, cols: list[str], rows: list[list], last_row_id=None, changes=0):
        self._rows = [D1Row(cols, r) for r in rows]
        self.lastrowid = last_row_id
        self.rowcount = changes
        self._i = 0

    def fetchone(self):
        if self._i >= len(self._rows):
            return None
        self._i += 1
        return self._rows[self._i - 1]

    def fetchall(self):
        out, self._i = self._rows[self._i:], len(self._rows)
        return out

    def __iter__(self):
        return iter(self.fetchall())


_http = threading.local()


def _client() -> httpx.Client:
    if not getattr(_http, "c", None):
        # Free hosting: the Worker's /__d1 route is public, so it checks this token.
        token = os.getenv("INTERNAL_TOKEN", "")
        _http.c = httpx.Client(timeout=60, headers={"x-internal-token": token} if token else None)
    return _http.c


def _norm(v):
    if isinstance(v, bool):
        return int(v)
    return v


class D1Connection:
    """Sends statements to the Worker's D1 handler. Each statement commits on its own (D1 has no
    cross-request transactions); executemany sends one atomic batch."""

    def _call(self, statements: list[dict]) -> list[dict]:
        r = _client().post(f"{D1_PROXY_URL}/query", json={"statements": statements})
        if r.status_code != 200:
            raise sqlite3.OperationalError(f"D1 error {r.status_code}: {r.text[:300]}")
        data = r.json()
        if data.get("error"):
            msg = data["error"]
            cls = sqlite3.IntegrityError if "constraint" in msg.lower() else sqlite3.OperationalError
            raise cls(msg)
        return data["results"]

    def execute(self, sql: str, params=()) -> D1Cursor:
        res = self._call([{"sql": sql, "params": [_norm(p) for p in (params or ())]}])[0]
        return D1Cursor(res.get("columns") or [], res.get("rows") or [], res.get("last_row_id"), res.get("changes", 0))

    def executemany(self, sql: str, seq) -> D1Cursor:
        stmts = [{"sql": sql, "params": [_norm(p) for p in params]} for params in seq]
        for k in range(0, len(stmts), 50):
            self._call(stmts[k:k + 50])
        return D1Cursor([], [])

    def executescript(self, script: str) -> None:
        stmts = [{"sql": x, "params": []} for x in split_sql(script)]
        for k in range(0, len(stmts), 25):
            self._call(stmts[k:k + 25])

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def split_sql(script: str) -> list[str]:
    """Statements of a schema script, comments removed (no semicolons appear inside our string literals)."""
    no_comments = re.sub(r"--[^\n]*", "", script)
    return [x.strip() for x in no_comments.split(";") if x.strip()]


def using_d1() -> bool:
    return bool(D1_PROXY_URL)


@contextmanager
def session():
    if using_d1():
        yield D1Connection()
        return
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after the first release; existing databases are upgraded in place.
MIGRATIONS = {
    "company": [("watch", "INTEGER DEFAULT 0"), ("last_researched_at", "TEXT"), ("workspace_id", "INTEGER NOT NULL DEFAULT 1")],
    "seller_doc": [("workspace_id", "INTEGER NOT NULL DEFAULT 1")],
    "feedback": [("workspace_id", "INTEGER NOT NULL DEFAULT 1")],
    "document": [("fetched_at", "TEXT")],
    "person": [("function", "TEXT"), ("reports_to", "TEXT"), ("reports_to_source", "TEXT"), ("document_id", "INTEGER")],
    "initiative": [("feedback", "TEXT"), ("basis", "TEXT")],
    "vendor": [("deal_type", "TEXT"), ("deal_value", "TEXT"), ("deal_date", "TEXT"), ("duration", "TEXT"), ("scope", "TEXT")],
    "initiative_contact": [("feedback", "TEXT"), ("source", "TEXT")],
}


def _rebuild_for_workspaces() -> None:
    """Databases from before workspaces: company names were unique globally and title learning was global.
    Rebuild those two tables with per-workspace keys (SQLite's copy-and-swap method, with foreign keys off
    so nothing that points at `company` is touched). Existing rows go to workspace 1."""
    if not Path(config.DB_PATH).exists():
        return
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        stmts = {x.split("(")[0].split()[-1]: x for x in split_sql(SCHEMA)}
        for table, extra in (("company", ""), ("title_stats", "")):
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
            if not cols or "workspace_id" in cols:
                continue
            create = stmts[table].replace(f"CREATE TABLE IF NOT EXISTS {table} (", f"CREATE TABLE {table}_new (", 1)
            conn.execute(create)
            new_cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table}_new)")}
            for r in conn.execute(f"PRAGMA table_info({table})").fetchall():  # columns added by later migrations
                if r["name"] not in new_cols:
                    conn.execute(f"ALTER TABLE {table}_new ADD COLUMN {r['name']} {r['type'] or 'TEXT'}"
                                 + (f" DEFAULT {r['dflt_value']}" if r["dflt_value"] is not None else ""))
            conn.execute(f"INSERT INTO {table}_new({', '.join(cols)}, workspace_id) SELECT {', '.join(cols)}, 1 FROM {table}")
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
            conn.commit()
    finally:
        conn.close()


def init() -> None:
    if not using_d1():
        _rebuild_for_workspaces()
    with session() as s:
        s.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in s.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    s.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        if not s.execute("SELECT 1 FROM workspace LIMIT 1").fetchone():
            # everything researched before workspaces existed belongs to the first one
            name = "Moolya"
            try:
                from . import profiles
                name = profiles.legacy_company_name() or name
            except Exception:
                pass
            s.execute("INSERT INTO workspace(id, name) VALUES (1, ?)", (name,))


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def append_log(run_id: int, message: str) -> None:
    with session() as s:
        log = json.loads(s.execute("SELECT log FROM run WHERE id=?", (run_id,)).fetchone()["log"])
        log.append(message)
        s.execute("UPDATE run SET log=? WHERE id=?", (json.dumps(log), run_id))


def kept_initiatives(company_id: int) -> list[dict]:
    """Initiatives with work on them (emails fetched, contacts or the initiative marked right/wrong, or confirmed).
    A re-run updates these in place instead of deleting them."""
    with session() as s:
        return [dict(r) for r in s.execute(
            """SELECT * FROM initiative i WHERE i.company_id=? AND (COALESCE(i.feedback,'') NOT IN ('', 'dismissed')
               OR EXISTS (SELECT 1 FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
                          WHERE ic.initiative_id=i.id AND (ic.feedback IS NOT NULL OR p.email IS NOT NULL OR p.phone IS NOT NULL)))""",
            (company_id,))]


def clear_company_results(company_id: int) -> list[dict]:
    """A refresh rebuilds initiatives and links, but keeps initiatives you've worked on and their enriched or
    reviewed contacts. Documents and people are always kept. Returns the kept initiatives."""
    kept = kept_initiatives(company_id)
    keep_ids = {k["id"] for k in kept}
    with session() as s:
        ids = [r["id"] for r in s.execute("SELECT id FROM initiative WHERE company_id=?", (company_id,))]
        for iid in ids:
            if iid in keep_ids:  # drop only untouched suggestions; they get re-ranked
                s.execute("""DELETE FROM initiative_contact WHERE initiative_id=? AND (feedback='rejected' OR (feedback IS NULL
                             AND person_id IN (SELECT id FROM person WHERE email IS NULL AND phone IS NULL)))""", (iid,))
                continue
            s.execute("DELETE FROM initiative_contact WHERE initiative_id=?", (iid,))
            s.execute("DELETE FROM initiative_evidence WHERE initiative_id=?", (iid,))
            s.execute("DELETE FROM initiative WHERE id=?", (iid,))
        s.execute("DELETE FROM vendor WHERE company_id=?", (company_id,))
        s.execute("DELETE FROM location WHERE company_id=?", (company_id,))
        s.execute("DELETE FROM job_location WHERE company_id=?", (company_id,))
    return kept
