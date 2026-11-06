"""Copy the accounts you researched on your Mac into the cloud database.

    python scripts/export_for_d1.py                 # writes d1_import.sql
    npx wrangler d1 execute accountscope --remote --file=d1_import.sql

Run it after the first deploy, once you've opened the site and signed in (that creates the tables).
Everything lands in the first workspace (yours). Users, sessions and the API cache are not copied.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import config, db  # noqa: E402

# parents before children, so references resolve in order
TABLES = ["company", "run", "document", "initiative", "initiative_evidence", "person", "initiative_contact", "vendor",
          "tech", "location", "job_location", "project", "project_evidence", "project_contact", "person_sample",
          "buyer_brief", "pitch", "alert", "feedback", "title_stats", "seller_doc"]
MAX_TEXT = 90_000  # D1 caps one SQL statement at 100 KB


def lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, bytes):
        return "X'" + v.hex() + "'"
    s = str(v)[:MAX_TEXT]
    return "'" + s.replace("'", "''") + "'"


def main(out_path: str = "d1_import.sql") -> None:
    db.init()  # brings an older local database up to the current schema first
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    lines = []
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts = {}
    for t in TABLES:
        if t not in have:
            continue
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        counts[t] = len(rows)
        for r in rows:
            cols = r.keys()
            lines.append(f"INSERT OR REPLACE INTO {t}({', '.join(cols)}) VALUES ({', '.join(lit(r[c]) for c in cols)});")
    ws = conn.execute("SELECT name, profile FROM workspace WHERE id=1").fetchone()
    profile = ws["profile"] if ws and ws["profile"] else None
    if not profile:
        from backend import profiles, tenancy
        with tenancy.use(1):
            profile = json.dumps(profiles.load(1))
    lines.append(f"UPDATE workspace SET name={lit(ws['name'] if ws else 'Moolya')}, profile={lit(profile)} WHERE id=1;")
    Path(out_path).write_text("\n".join(lines) + "\n")
    print(f"Wrote {out_path}: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    print("Next: npx wrangler d1 execute accountscope --remote --file=" + out_path)


if __name__ == "__main__":
    main(*sys.argv[1:])
