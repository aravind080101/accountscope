"""Watchlists and alerts.

Before each research run we snapshot what we knew; after it we diff and raise alerts for:
new initiatives, initiatives moving stage, new leaders named, hiring surges, new vendors.
Watched accounts are re-researched every WATCH_INTERVAL_DAYS by a background thread while the
app runs, or by `python -m backend.watch` from cron if you host it elsewhere.
"""
import threading
import time
from datetime import datetime, timedelta, timezone

from . import config, db
from .feedback import same_initiative
from .orgchart import rank_of
from .taxonomy import STAGES


def _jobs_last_30d(s, company_id: int) -> int:
    db.fail_stale_runs()  # a dead run must not block its account's watch forever
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    return s.execute(
        """SELECT COUNT(*) n FROM document WHERE company_id=? AND source_type='jobs'
           AND COALESCE(published_at, fetched_at, '') >= ?""", (company_id, cutoff)).fetchone()["n"]


def snapshot(company_id: int) -> dict:
    with db.session() as s:
        inits = db.rows(s.execute("SELECT name, stage, category, summary FROM initiative WHERE company_id=?", (company_id,)))
        named = db.rows(s.execute(
            """SELECT DISTINCT p.full_name, p.title FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
               JOIN initiative i ON i.id=ic.initiative_id WHERE i.company_id=? AND ic.source='evidence'""", (company_id,)))
        vendors = [r["name"] for r in s.execute("SELECT name FROM vendor WHERE company_id=?", (company_id,))]
        jobs = _jobs_last_30d(s, company_id)
        had_run = s.execute("SELECT COUNT(*) n FROM run WHERE company_id=? AND status='done'", (company_id,)).fetchone()["n"] > 0
    return {"initiatives": inits, "named": {p["full_name"].lower() for p in named}, "vendors": {v.lower() for v in vendors},
            "jobs": jobs, "had_run": had_run}


def diff_and_store(company_id: int, before: dict) -> list[dict]:
    if not before["had_run"]:
        return []  # first research: everything is new, so no alerts
    after = snapshot(company_id)
    out = []
    for i in after["initiatives"]:
        prev = next((p for p in before["initiatives"] if same_initiative(p["name"], i["name"])), None)
        if not prev:
            out.append(("new_initiative", f"New initiative: {i['name']}", i["summary"]))
        elif STAGES.index(i["stage"]) > STAGES.index(prev["stage"]):
            label = i["stage"].replace("_", " ")
            out.append(("stage_change", f"{i['name']} moved to {label}", f"Was {prev['stage'].replace('_', ' ')}."))
    with db.session() as s:
        named_now = db.rows(s.execute(
            """SELECT DISTINCT p.full_name, p.title FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
               JOIN initiative i ON i.id=ic.initiative_id WHERE i.company_id=? AND ic.source='evidence'""", (company_id,)))
        vendors_now = db.rows(s.execute("SELECT name, relationship, area FROM vendor WHERE company_id=?", (company_id,)))
    for p in named_now:
        if p["full_name"].lower() not in before["named"] and rank_of(p["title"]) <= 4:
            out.append(("new_leader", f"New leader in the news: {p['full_name']}", p["title"]))
    if after["jobs"] >= 5 and after["jobs"] >= before["jobs"] + 3:
        out.append(("hiring_surge", f"Hiring surge: {after['jobs']} job posts in the last 30 days",
                    f"Up from {before['jobs']} at the previous check."))
    for v in vendors_now:
        if v["name"].lower() not in before["vendors"]:
            out.append(("new_vendor", f"New vendor: {v['name']}", f"{v['relationship'] or 'linked'} for {v['area'] or 'unspecified area'}"))
    with db.session() as s:
        for kind, title, detail in out:
            s.execute("INSERT INTO alert(company_id, kind, title, detail) VALUES (?,?,?,?)", (company_id, kind, title, detail))
    return [{"kind": k, "title": t, "detail": d} for k, t, d in out]


# ------------------------------------------------------------------ scheduler


def due_accounts() -> list[int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.WATCH_INTERVAL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    with db.session() as s:
        return [r["id"] for r in s.execute(
            """SELECT c.id FROM company c WHERE c.watch=1 AND COALESCE(c.last_researched_at, '') < ?
               AND NOT EXISTS (SELECT 1 FROM run r WHERE r.company_id=c.id AND r.status IN ('queued','running'))""",
            (cutoff,))]


def refresh_due(run_fn) -> int:
    ids = due_accounts()
    for cid in ids:
        with db.session() as s:
            rid = s.execute("INSERT INTO run(company_id, updated_at) VALUES (?, CURRENT_TIMESTAMP)", (cid,)).lastrowid
        run_fn(rid, cid, force=True)
    return len(ids)


def start_scheduler(run_fn, every_minutes: int = 30) -> None:
    if not config.WATCH_SCHEDULER:
        return

    def loop():
        time.sleep(20)
        while True:
            try:
                if config.configured():
                    refresh_due(run_fn)
            except Exception:
                pass
            time.sleep(every_minutes * 60)

    threading.Thread(target=loop, daemon=True, name="watchlist").start()
