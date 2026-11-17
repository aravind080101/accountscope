"""HTTP API + static frontend.  Run:  uvicorn backend.app:app --reload"""
import csv
import hmac
from contextlib import asynccontextmanager
import io
import json
import re
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import alerts, auth, buyers, campaigns, config, costs, db, discover, feedback, guard, llm, orgchart, pipeline, pitch, profiles, projects, tenancy
from .providers import apollo
from .taxonomy import CATEGORIES

FRONTEND = config.ROOT / "frontend"
db.init()
auth.bootstrap()
db.fail_interrupted_runs()  # runs from a previous process died with it


@asynccontextmanager
async def lifespan(_app):
    if not config.RUNNING_IN_CLOUD:  # in the cloud a Cloudflare Cron Trigger calls /api/internal/watch instead
        alerts.start_scheduler(pipeline.run)  # re-researches watched accounts while the app runs
    yield


app = FastAPI(title="AccountScope", version="0.4.0", lifespan=lifespan)
app.middleware("http")(auth.middleware)


@app.middleware("http")
async def scrub_secrets(request, call_next):
    """Never send an API key or token to the browser, whatever message it ended up in."""
    resp = await call_next(request)
    if not resp.headers.get("content-type", "").startswith("application/json"):
        return resp
    body = b"".join([chunk async for chunk in resp.body_iterator])
    clean = config.redact(body.decode("utf-8", "replace")).encode("utf-8")
    headers = {k: v for k, v in resp.headers.items() if k.lower() != "content-length"}
    return Response(content=clean, status_code=resp.status_code, headers=headers, media_type=resp.media_type)


@app.middleware("http")
async def proxy_only(request, call_next):
    """Registered after auth, so it runs first: refuse anything that didn't come through the Worker."""
    if config.PROXY_ONLY and request.url.path != "/health":
        if not config.INTERNAL_TOKEN or not hmac.compare_digest(
                request.headers.get("x-proxy-token", ""), config.INTERNAL_TOKEN):
            return JSONResponse({"detail": "Open AccountScope through its workers.dev address."}, status_code=403)
    return await call_next(request)

app.include_router(auth.router)


@app.get("/health")
def container_health():
    """Readiness check for the Cloudflare container (no data, no login)."""
    return {"ok": True}


@app.post("/api/internal/watch")
def internal_watch(background: BackgroundTasks):
    """Called by the Cloudflare Cron Trigger: re-research watched accounts that are due."""
    background.add_task(alerts.refresh_due, pipeline.run)
    return {"queued": len(alerts.due_accounts())}


class AccountIn(BaseModel):
    name: str
    domain: str | None = None


class BulkIn(BaseModel):
    companies: list[AccountIn]


class ProfileGenIn(BaseModel):
    company: str = ""
    description: str = ""


class SellerTarget(BaseModel):
    name: str
    domain: str | None = None


class WebResearchIn(BaseModel):
    targets: list[SellerTarget]


# ------------------------------------------------------------------ meta


def _seller_name():
    try:
        return profiles.load().get("company")
    except RuntimeError:
        return None


def _seller_domain():
    """The seller's website, for its logo: the profile's domain, else one of its own web sources, else <name>.com."""
    try:
        prof = profiles.load()
    except RuntimeError:
        return None
    d = (prof.get("domain") or prof.get("website") or "").strip()
    name = (prof.get("company") or "").strip()
    if not d and name:
        first = re.sub(r"[^a-z0-9]", "", name.lower().split()[0])
        try:
            for src in profiles.list_sources():
                host = re.sub(r"^https?://(www\.)?", "", src.get("url") or "").split("/")[0].lower()
                if first and host.startswith(first + "."):
                    d = host
                    break
        except Exception:
            pass
        d = d or (f"{first}.com" if first else "")
    return re.sub(r"^https?://(www\.)?", "", d).split("/")[0] or None


@app.get("/api/health")
def health():
    missing = []
    if not config.llm_provider():
        missing.append("ANTHROPIC_API_KEY or OPENAI_API_KEY")
    if not config.TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    return {
        "configured": config.configured(),
        "llm_provider": config.llm_provider(),
        "missing_keys": missing,
        "people_search": apollo.available(),
        "seller": _seller_name(),
        "seller_domain": _seller_domain(),
        "builtwith": bool(config.BUILTWITH_API_KEY),
        "cloud": config.RUNNING_IN_CLOUD,
    }


@app.get("/api/profile")
def get_profile():
    return {"profile": profiles.load(), "categories": {k: v["label"] for k, v in CATEGORIES.items()}}


@app.put("/api/profile")
def put_profile(profile: dict):
    if not profile.get("offerings"):
        raise HTTPException(400, "A profile needs at least one offering")
    return profiles.save(profile)


@app.post("/api/profile/generate")
def generate_profile(body: ProfileGenIn):
    if not llm.available():
        raise HTTPException(400, "Building a profile needs OPENAI_API_KEY or ANTHROPIC_API_KEY; you can still edit the JSON by hand")
    try:
        return profiles.build(body.company, body.description)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/profile/sources")
def seller_sources():
    return profiles.list_sources(include_campaigns=True)


@app.post("/api/profile/sources")
async def upload_sources(files: list[UploadFile] = File(...), kind: str = "deck", campaign_id: int | None = None):
    """kind=deck: what you sell (offerings). kind=pov: the CEO's/founder's decks, posts and talks (points of view).
    campaign_id files the decks under that campaign instead of the general library."""
    if kind not in ("deck", "pov"):
        raise HTTPException(400, "kind must be deck or pov")
    if campaign_id is not None:
        if kind != "deck":
            raise HTTPException(400, "Only decks can be assigned to a campaign")
        _campaign(campaign_id)
    added, errors = [], []
    for f in files:
        try:
            added.append(profiles.add_source(f.filename, kind, profiles.read_file(f.filename, await f.read()), campaign_id=campaign_id))
        except Exception as exc:
            errors.append(f"{f.filename}: {exc}")
    if errors and not added:
        raise HTTPException(400, "; ".join(errors))
    return {"added": added, "errors": errors}


class PovUrlIn(BaseModel):
    url: str


@app.post("/api/profile/pov/url")
def add_pov_url(body: PovUrlIn):
    """Add a public page by the CEO/founder (blog post, article, talk transcript) to the POV library."""
    if not config.TAVILY_API_KEY:
        raise HTTPException(400, "Reading a page needs TAVILY_API_KEY")
    from .providers import tavily
    try:
        page = tavily.extract(body.url)
        return profiles.add_source(page["title"], "pov", page["text"][:60_000], body.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Couldn't read that page: {config.redact(str(exc))}") from exc


@app.post("/api/profile/pov")
def build_pov():
    if not llm.available():
        raise HTTPException(400, "Building points of view needs an AI key")
    try:
        return profiles.build_pov()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class AssignIn(BaseModel):
    campaign_id: int | None = None


@app.put("/api/profile/sources/{sid}/campaign")
def assign_source(sid: int, body: AssignIn):
    try:
        return profiles.assign_source(sid, body.campaign_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/profile/sources/{sid}")
def remove_source(sid: int):
    profiles.delete_source(sid)
    return {"ok": True}


@app.post("/api/profile/research")
def research_seller(body: WebResearchIn):
    if not config.TAVILY_API_KEY:
        raise HTTPException(400, "Web research needs TAVILY_API_KEY")
    added = profiles.research_web([t.model_dump() for t in body.targets if t.name.strip()])
    return {"added": len(added), "sources": profiles.list_sources(include_campaigns=True)}


_rescore: dict[int, dict] = {}   # per workspace


def _rescore_all(wid: int):
    with tenancy.use(wid):
        with db.session() as s:
            ids = [r["id"] for r in s.execute("SELECT id FROM company WHERE workspace_id=?", (wid,))]
        st = _rescore[wid] = {"running": True, "done": 0, "total": len(ids)}
        try:
            for cid in ids:
                try:
                    profiles.rescore_company(cid)
                except Exception:
                    pass
                st["done"] += 1
        finally:
            st["running"] = False


@app.post("/api/profile/rescore")
def rescore(background: BackgroundTasks):
    if not llm.available():
        raise HTTPException(400, "Re-scoring needs an AI key")
    wid = tenancy.current()
    st = _rescore.get(wid) or {"running": False, "done": 0, "total": 0}
    if not st["running"]:
        background.add_task(_rescore_all, wid)
    return st


@app.get("/api/profile/rescore")
def rescore_status():
    return _rescore.get(tenancy.current()) or {"running": False, "done": 0, "total": 0}


# ------------------------------------------------------------------ accounts


def _require_keys():
    if not config.configured():
        raise HTTPException(400, "Add TAVILY_API_KEY plus ANTHROPIC_API_KEY or OPENAI_API_KEY to .env, then restart the app.")


def _queue_run(company_id: int) -> int:
    with db.session() as s:
        return s.execute("INSERT INTO run(company_id, updated_at) VALUES (?, CURRENT_TIMESTAMP)", (company_id,)).lastrowid


def _start_run(company_id: int, tasks: BackgroundTasks, force: bool = False) -> int:
    _require_keys()
    live = db.active_run(company_id)
    if live:  # already researching (e.g. the button was clicked several times while the server was slow)
        return live
    run_id = _queue_run(company_id)
    tasks.add_task(pipeline.run, run_id, company_id, force)
    return run_id


def _upsert_company(name: str, domain: str | None) -> int:
    name = name.strip()
    if not name:
        raise HTTPException(400, "Company name is required")
    domain = (domain or "").strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").strip("/") or None
    with db.session() as s:
        wid = tenancy.current()
        row = s.execute("SELECT id FROM company WHERE workspace_id=? AND lower(name)=lower(?)", (wid, name)).fetchone()
        cid = row["id"] if row else s.execute("INSERT INTO company(workspace_id, name, domain) VALUES (?,?,?)",
                                              (wid, name, domain)).lastrowid
        if row and domain:
            s.execute("UPDATE company SET domain=? WHERE id=?", (domain, cid))
    return cid


@app.get("/api/accounts")
def list_accounts():
    with db.session() as s:
        rows = db.rows(s.execute(
            """SELECT c.id, c.name, c.domain, c.industry, c.hq_country, c.watch, c.last_researched_at,
               (SELECT COUNT(*) FROM initiative i WHERE i.company_id=c.id AND COALESCE(i.feedback,'')!='dismissed') AS initiatives,
               (SELECT COUNT(*) FROM project p WHERE p.company_id=c.id AND COALESCE(p.feedback,'')!='dismissed') AS projects,
               (SELECT COUNT(*) FROM alert a WHERE a.company_id=c.id AND a.read=0) AS unread,
               (SELECT COUNT(*) FROM document d WHERE d.company_id=c.id) AS documents,
               (SELECT status FROM run r WHERE r.company_id=c.id ORDER BY r.id DESC LIMIT 1) AS status
               FROM company c WHERE c.workspace_id=? ORDER BY c.id DESC""", (tenancy.current(),)))
        for r in rows:
            best = s.execute(
                """SELECT i.id, i.name, i.fit_score, i.stage, i.basis FROM initiative i WHERE i.company_id=?
                   AND COALESCE(i.feedback,'')!='dismissed' ORDER BY i.fit_score DESC, i.confidence DESC LIMIT 1""", (r["id"],)).fetchone()
            r["best"] = dict(best) if best else None
            owner = None
            if best:
                owner = s.execute(
                    """SELECT p.full_name, p.title, ic.role FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
                       WHERE ic.initiative_id=? AND COALESCE(ic.feedback,'')!='rejected'
                       ORDER BY ic.role='Owner' DESC, ic.score DESC LIMIT 1""", (best["id"],)).fetchone()
            r["owner"] = dict(owner) if owner else None
    return rows


@app.post("/api/accounts")
def add_account(body: AccountIn, tasks: BackgroundTasks):
    _require_keys()
    cid = _upsert_company(body.name, body.domain)
    return {"company_id": cid, "run_id": _start_run(cid, tasks)}


@app.post("/api/accounts/bulk")
def add_accounts_bulk(body: BulkIn, tasks: BackgroundTasks):
    """Queue many companies; they are researched one after another to respect API rate limits."""
    _require_keys()
    if not body.companies or len(body.companies) > 500:
        raise HTTPException(400, "Send between 1 and 500 companies per batch")
    jobs = []
    for c in body.companies:
        if c.name.strip():
            cid = _upsert_company(c.name, c.domain)
            if db.active_run(cid):  # already being researched
                continue
            jobs.append((_queue_run(cid), cid))

    def run_all():
        with pipeline.keep_alive([rid for rid, _ in jobs]):  # queued ones wait their turn without being failed
            for run_id, cid in jobs:
                pipeline.run(run_id, cid)

    tasks.add_task(run_all)
    return {"queued": len(jobs), "company_ids": [cid for _, cid in jobs]}


@app.post("/api/accounts/{cid}/refresh")
def refresh(cid: int, tasks: BackgroundTasks, force: bool = False):
    guard.company(cid)
    """force=true searches the web again even if sources were fetched recently."""
    _company(cid)
    return {"company_id": cid, "run_id": _start_run(cid, tasks, force)}


class WatchIn(BaseModel):
    watch: bool


@app.post("/api/accounts/{cid}/watch")
def set_watch(cid: int, body: WatchIn):
    guard.company(cid)
    _company(cid)
    with db.session() as s:
        s.execute("UPDATE company SET watch=? WHERE id=?", (int(body.watch), cid))
    return {"company_id": cid, "watch": body.watch, "every_days": config.WATCH_INTERVAL_DAYS}


@app.get("/api/accounts/{cid}/org")
def org(cid: int):
    guard.company(cid)
    _company(cid)
    return orgchart.build(cid)


@app.get("/api/accounts/{cid}/tech")
def tech(cid: int):
    guard.company(cid)
    _company(cid)
    with db.session() as s:
        vendors = db.rows(s.execute(
            """SELECT v.name, v.relationship, v.area, v.quote, v.is_competitor, v.deal_type, v.deal_value, v.deal_date,
               v.duration, d.url, d.title doc_title, d.published_at
               FROM vendor v LEFT JOIN document d ON d.id=v.document_id WHERE v.company_id=?
               ORDER BY COALESCE(v.deal_date, d.published_at, '') DESC, v.is_competitor DESC, v.name""", (cid,)))
        stack = db.rows(s.execute(
            """SELECT t.name, t.category, t.source, d.url FROM tech t LEFT JOIN document d ON d.id=t.document_id
               WHERE t.company_id=? ORDER BY t.source IN ('website','builtwith'), lower(t.name)""", (cid,)))
    return {"vendors": vendors, "tech": stack}


@app.get("/api/summary")
def summary():
    """Numbers and highlights for the home dashboard."""
    with db.session() as s:
        wid = tenancy.current()
        n = lambda q: s.execute(q, (wid,)).fetchone()[0]  # noqa: E731
        totals = {
            "accounts": n("SELECT COUNT(*) FROM company WHERE workspace_id=?"),
            "watched": n("SELECT COUNT(*) FROM company WHERE watch=1 AND workspace_id=?"),
            "projects": n("""SELECT COUNT(*) FROM initiative i JOIN company c ON c.id=i.company_id
                             WHERE COALESCE(i.feedback,'')!='dismissed' AND c.workspace_id=?"""),
            "owners": n("""SELECT COUNT(DISTINCT ic.person_id) FROM initiative_contact ic JOIN initiative i ON i.id=ic.initiative_id
                           JOIN company c ON c.id=i.company_id WHERE ic.role='Owner'
                           AND COALESCE(ic.feedback,'')!='rejected' AND c.workspace_id=?"""),
            "unread": n("SELECT COUNT(*) FROM alert a JOIN company c ON c.id=a.company_id WHERE a.read=0 AND c.workspace_id=?"),
        }
        top = db.rows(s.execute(
            """SELECT i.id, i.name, i.stage, i.fit_score, i.basis, i.category, c.id company_id, c.name company,
               (SELECT p.full_name FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
                 WHERE ic.initiative_id=i.id AND COALESCE(ic.feedback,'')!='rejected' ORDER BY ic.score DESC LIMIT 1) top_contact,
               (SELECT p.title FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
                 WHERE ic.initiative_id=i.id AND COALESCE(ic.feedback,'')!='rejected' ORDER BY ic.score DESC LIMIT 1) top_title
               FROM initiative i JOIN company c ON c.id=i.company_id WHERE COALESCE(i.feedback,'')!='dismissed'
               AND c.workspace_id=? ORDER BY i.fit_score DESC, i.confidence DESC LIMIT 8""", (wid,)))
        recent = db.rows(s.execute(
            """SELECT a.id, a.kind, a.title, a.created_at, a.read, c.id company_id, c.name company FROM alert a
               JOIN company c ON c.id=a.company_id WHERE c.workspace_id=? ORDER BY a.id DESC LIMIT 6""", (wid,)))
    for t in top:
        t["category_label"] = CATEGORIES.get(t["category"], CATEGORIES["other"])["label"]
    return {"totals": totals, "top_projects": top, "recent_alerts": recent}


@app.get("/api/accounts/{cid}/footprint")
def footprint(cid: int):
    guard.company(cid)
    _company(cid)
    with db.session() as s:
        sites = db.rows(s.execute(
            """SELECT l.city, l.country, l.type, l.functions, l.headcount, l.quote, d.url, d.title doc_title
               FROM location l LEFT JOIN document d ON d.id=l.document_id WHERE l.company_id=?
               ORDER BY l.type='hq' DESC, l.country, l.city""", (cid,)))
        hiring = db.rows(s.execute(
            "SELECT city, country, roles, functions FROM job_location WHERE company_id=? ORDER BY roles DESC", (cid,)))
    for r in sites + hiring:
        r["functions"] = json.loads(r["functions"] or "[]")
    return {"sites": sites, "hiring": hiring}


@app.get("/api/people/{pid}/brief")
def get_brief(pid: int):
    guard.person(pid)
    b = buyers.get(pid)
    if not b:
        raise HTTPException(404, "No brief yet")
    return b


class SampleIn(BaseModel):
    text: str
    kind: str = "post"


@app.get("/api/people/{pid}/samples")
def person_samples(pid: int):
    guard.person(pid)
    return buyers.samples(pid)


@app.post("/api/people/{pid}/samples")
def add_person_sample(pid: int, body: SampleIn):
    guard.person(pid)
    try:
        return buyers.add_sample(pid, body.text, body.kind)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/samples/{sid}")
def remove_sample(sid: int):
    guard.sample(sid)
    buyers.delete_sample(sid)
    return {"ok": True}


@app.post("/api/people/{pid}/brief")
def make_brief(pid: int, force: bool = False):
    guard.person(pid)
    _require_keys()
    try:
        return buyers.build(pid, force)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Couldn't build the brief: {exc}") from exc


# ------------------------------------------------------------------ alerts


@app.get("/api/alerts")
def list_alerts(company_id: int | None = None, unread: bool = False):
    q = """SELECT a.*, c.name company FROM alert a JOIN company c ON c.id=a.company_id WHERE c.workspace_id=?"""
    args: list = [tenancy.current()]
    if company_id:
        q += " AND a.company_id=?"
        args.append(company_id)
    if unread:
        q += " AND a.read=0"
    with db.session() as s:
        rows = db.rows(s.execute(q + " ORDER BY a.id DESC LIMIT 300", args))
        n_unread = s.execute("SELECT COUNT(*) n FROM alert a JOIN company c ON c.id=a.company_id WHERE a.read=0 AND c.workspace_id=?",
                             (tenancy.current(),)).fetchone()["n"]
    return {"alerts": rows, "unread": n_unread}


class ReadIn(BaseModel):
    ids: list[int] | None = None
    company_id: int | None = None


@app.post("/api/alerts/read")
def mark_read(body: ReadIn):
    with db.session() as s:
        mine = "company_id IN (SELECT id FROM company WHERE workspace_id=?)"
        if body.ids:
            s.executemany(f"UPDATE alert SET read=1 WHERE id=? AND {mine}", [(i, tenancy.current()) for i in body.ids])
        elif body.company_id:
            s.execute(f"UPDATE alert SET read=1 WHERE company_id=? AND {mine}", (body.company_id, tenancy.current()))
        else:
            s.execute(f"UPDATE alert SET read=1 WHERE {mine}", (tenancy.current(),))
    return {"ok": True}


# ------------------------------------------------------------------ feedback


class VerdictIn(BaseModel):
    verdict: str


@app.post("/api/contacts/{icid}/feedback")
def contact_feedback(icid: int, body: VerdictIn):
    guard.contact(icid)
    try:
        return feedback.record_contact(icid, body.verdict)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/initiatives/{iid}/feedback")
def initiative_feedback(iid: int, body: VerdictIn):
    guard.initiative(iid)
    try:
        return feedback.record_initiative(iid, body.verdict)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete("/api/accounts/{cid}")
def delete_account(cid: int):
    _company(cid)
    db.clear_company_results(cid)
    with db.session() as s:
        s.execute("DELETE FROM buyer_brief WHERE person_id IN (SELECT id FROM person WHERE company_id=?)", (cid,))
        for t in ("person", "document", "run", "tech", "alert", "feedback", "location", "job_location"):
            s.execute(f"DELETE FROM {t} WHERE company_id=?", (cid,))
        s.execute("DELETE FROM company WHERE id=?", (cid,))
    return {"deleted": cid}


def _company(cid: int) -> dict:
    with db.session() as s:
        row = s.execute("SELECT * FROM company WHERE id=? AND workspace_id=?", (cid, tenancy.current())).fetchone()
    if not row:
        raise HTTPException(404, "Account not found")
    return dict(row)


@app.get("/api/accounts/{cid}")
def account_detail(cid: int):
    company = _company(cid)
    with db.session() as s:
        inits = db.rows(
            s.execute("""SELECT * FROM initiative WHERE company_id=? AND COALESCE(feedback,'')!='dismissed'
                         ORDER BY feedback='confirmed' DESC, fit_score DESC, confidence DESC""", (cid,))
        )
        dismissed = s.execute("SELECT COUNT(*) n FROM initiative WHERE company_id=? AND feedback='dismissed'", (cid,)).fetchone()["n"]
        for i in inits:
            i["tech"] = json.loads(i["tech"] or "[]")
            i["category_label"] = CATEGORIES.get(i["category"], CATEGORIES["other"])["label"]
            i["evidence"] = db.rows(
                s.execute(
                    """SELECT d.source_type, d.url, d.title, d.published_at, e.quote FROM initiative_evidence e
                       JOIN document d ON d.id=e.document_id WHERE e.initiative_id=? ORDER BY d.published_at DESC""",
                    (i["id"],),
                )
            )
            i["contacts"] = db.rows(
                s.execute(
                    """SELECT ic.id, ic.role, ic.score, ic.rationale, ic.opener, ic.feedback, p.id person_id, p.full_name, p.title, p.email,
                       p.current, p.left_note, (SELECT 1 FROM buyer_brief b WHERE b.person_id=p.id) has_brief,
                       p.phone, p.linkedin_url, ic.source FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
                       WHERE ic.initiative_id=? ORDER BY ic.feedback='confirmed' DESC, ic.score DESC""",
                    (i["id"],),
                )
            )
        run = s.execute("SELECT * FROM run WHERE company_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        docs = s.execute("SELECT COUNT(*) n FROM document WHERE company_id=?", (cid,)).fetchone()["n"]
    run = dict(run) if run else None
    if run:
        run["log"] = json.loads(run["log"])
    with db.session() as s:
        unread = s.execute("SELECT COUNT(*) n FROM alert WHERE company_id=? AND read=0", (cid,)).fetchone()["n"]
        doc_mix = db.rows(s.execute("SELECT source_type, COUNT(*) n FROM document WHERE company_id=? GROUP BY source_type", (cid,)))
        # everyone found at the account, so leaders and anyone with a brief show even if no initiative names them
        people = db.rows(s.execute("""SELECT p.id person_id, p.full_name, p.title, p.linkedin_url, p.email, p.current, p.left_note,
       (SELECT 1 FROM buyer_brief b WHERE b.person_id=p.id) has_brief FROM person p WHERE p.company_id=?""", (cid,)))
    return {"company": company, "people": people, "initiatives": inits, "projects": projects.for_company(cid), "run": run, "documents": docs, "dismissed": dismissed,
            "unread_alerts": unread, "source_mix": {r["source_type"]: r["n"] for r in doc_mix},
            "watch_every_days": config.WATCH_INTERVAL_DAYS}


@app.get("/api/runs/{rid}")
def run_status(rid: int):
    guard.run(rid)
    with db.session() as s:
        row = s.execute("SELECT * FROM run WHERE id=?", (rid,)).fetchone()
    if not row:
        raise HTTPException(404, "Run not found")
    out = dict(row)
    out["log"] = json.loads(out["log"])
    return out


# ------------------------------------------------------------------ contacts


def find_linkedin(full_name: str, company: str) -> str | None:
    """A public LinkedIn profile URL for this person, from a web search (free). Only a /in/ page whose title has their name."""
    if not config.TAVILY_API_KEY or not full_name or "*" in full_name:
        return None
    from .providers import tavily
    try:
        results = tavily.raw_search(f'"{full_name}" {company} LinkedIn', max_results=6, include_domains=["linkedin.com"])
    except Exception:
        return None
    names = [w.lower() for w in full_name.split() if len(w) > 1]
    for r in results:
        url, title = (r.get("url") or ""), (r.get("title") or "").lower()
        if "linkedin.com/in/" in url and all(n in title for n in names[:2]):
            return url.split("?")[0]
    return None


def _enrich_person(pid: int) -> dict:
    with db.session() as s:
        row = s.execute("SELECT p.*, c.domain, c.name company FROM person p JOIN company c ON c.id=p.company_id WHERE p.id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "This person is no longer in the database. Reload the page.")
    p = dict(row)
    data, apollo_error = {}, None
    if apollo.available():
        try:
            data = apollo.enrich(p.get("apollo_id"), p["full_name"], p.get("domain"), p.get("company"))
        except Exception as exc:
            apollo_error = config.redact(str(exc))
    else:
        apollo_error = "APOLLO_API_KEY not set"
    full = (data.get("full_name") or "").strip()
    name = full if full and "*" not in full else p["full_name"]
    li_source = "apollo" if data.get("linkedin_url") else None
    if not data.get("linkedin_url") and not p.get("linkedin_url"):
        url = find_linkedin(name, p.get("company") or "")
        if url:
            data["linkedin_url"], li_source = url, "web search"
    with db.session() as s:
        s.execute(
            "UPDATE person SET email=COALESCE(?, email), phone=COALESCE(?, phone), linkedin_url=COALESCE(?, linkedin_url) WHERE id=?",
            (data.get("email"), data.get("phone"), data.get("linkedin_url"), p["id"]),
        )
        if full and "*" in p["full_name"] and "*" not in full:  # Apollo reveals the hidden surname
            clash = s.execute("SELECT 1 FROM person WHERE company_id=? AND full_name=? AND id!=?",
                              (p["company_id"], full, p["id"])).fetchone()
            if not clash:
                s.execute("UPDATE person SET full_name=? WHERE id=?", (full, p["id"]))
        cur = dict(s.execute("SELECT email, phone, linkedin_url FROM person WHERE id=?", (p["id"],)).fetchone())
    if not cur.get("email") and not cur.get("linkedin_url"):
        raise HTTPException(404 if not apollo_error else 502,
                            f"No email or LinkedIn found for {name}" + (f" (Apollo: {apollo_error})" if apollo_error else
                            ": Apollo has no match and the web search found no profile."))
    found = [k for k in ("email", "linkedin_url") if data.get(k)]
    missing = [k for k in ("email", "linkedin_url") if not cur.get(k)]
    return {**cur, "found": found, "missing": missing, "linkedin_source": li_source, "apollo_error": apollo_error}


@app.post("/api/people/{pid}/enrich")
def enrich_person(pid: int):
    guard.person(pid)
    """Get email by person id. People are never deleted by a re-run, so this id stays valid."""
    return _enrich_person(pid)


@app.post("/api/contacts/{icid}/enrich")
def enrich(icid: int):
    guard.contact(icid)
    with db.session() as s:
        row = s.execute("SELECT person_id FROM initiative_contact WHERE id=?", (icid,)).fetchone()
    if not row:
        raise HTTPException(404, "Contact not found")
    return _enrich_person(row["person_id"])


@app.post("/api/project-contacts/{pcid}/enrich")
def enrich_project_contact(pcid: int):
    guard.project_contact(pcid)
    with db.session() as s:
        row = s.execute("SELECT person_id FROM project_contact WHERE id=?", (pcid,)).fetchone()
    if not row:
        raise HTTPException(404, "Contact not found")
    return _enrich_person(row["person_id"])


@app.post("/api/project-contacts/{pcid}/feedback")
def project_contact_feedback(pcid: int, body: dict):
    guard.project_contact(pcid)
    verdict = body.get("verdict")
    if verdict not in ("confirmed", "rejected", "clear"):
        raise HTTPException(400, "verdict must be confirmed, rejected or clear")
    with db.session() as s:
        s.execute("UPDATE project_contact SET feedback=? WHERE id=?", (None if verdict == "clear" else verdict, pcid))
    return {"feedback": None if verdict == "clear" else verdict}


@app.post("/api/projects/{pid}/feedback")
def project_feedback(pid: int, body: dict):
    guard.project(pid)
    verdict = body.get("verdict")
    if verdict not in ("confirmed", "dismissed", "clear"):
        raise HTTPException(400, "verdict must be confirmed, dismissed or clear")
    with db.session() as s:
        s.execute("UPDATE project SET feedback=? WHERE id=?", (None if verdict == "clear" else verdict, pid))
    return {"feedback": None if verdict == "clear" else verdict}


# ------------------------------------------------------------------ pitches (outreach agent)


class PitchIn(BaseModel):
    kind: str | None = None        # initiative | project
    context_id: int | None = None
    campaign_id: int | None = None  # write it from this campaign's decks only


@app.post("/api/people/{pid}/pitch")
def make_pitch(pid: int, body: PitchIn, background: BackgroundTasks):
    guard.person(pid)
    if not llm.available():
        raise HTTPException(400, "Pitches need OPENAI_API_KEY or ANTHROPIC_API_KEY")
    if body.campaign_id and not campaigns.owns(body.campaign_id):
        raise HTTPException(404, "Campaign not found")
    try:
        ptid = pitch.create(pid, body.kind, body.context_id, body.campaign_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    background.add_task(pitch.run, ptid)
    return pitch.get(ptid)


@app.get("/api/people/{pid}/pitch")
def person_pitch(pid: int, campaign_id: int | None = None):
    guard.person(pid)
    p = pitch.latest_for_person(pid, campaign_id)
    if not p:
        raise HTTPException(404, "No pitch yet")
    return p


@app.get("/api/pitches")
def pitches(company_id: int | None = None, campaign_id: int | None = None, general: bool = False):
    """campaign_id: only that campaign's pitches. general=true: only pitches written outside any campaign."""
    if company_id:
        guard.company(company_id)
    return pitch.list_all(company_id, tenancy.current(), campaign_id, general)


@app.get("/api/pitches/{ptid}")
def one_pitch(ptid: int):
    guard.pitch(ptid)
    p = pitch.get(ptid)
    if not p:
        raise HTTPException(404, "Pitch not found")
    return p


class PitchEdit(BaseModel):
    messages: dict = {}
    status: str | None = None


@app.put("/api/pitches/{ptid}")
def edit_pitch(ptid: int, body: PitchEdit):
    guard.pitch(ptid)
    if body.status and body.status not in ("ready", "approved", "exported"):
        raise HTTPException(400, "status must be ready, approved or exported")
    try:
        return pitch.update_messages(ptid, body.messages, body.status)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


class BulkPitchIn(BaseModel):
    limit: int = 5
    min_fit: float = 0.5


@app.post("/api/accounts/{cid}/pitches")
def pitch_account(cid: int, body: BulkPitchIn, background: BackgroundTasks):
    guard.company(cid)
    if not llm.available():
        raise HTTPException(400, "Pitches need OPENAI_API_KEY or ANTHROPIC_API_KEY")
    people = pitch.top_contacts(cid, max(1, min(body.limit, 25)), body.min_fit)
    if not people:
        raise HTTPException(400, "No contacts on strong-fit initiatives or projects yet. Lower the fit bar or research the account first.")
    ids = [pitch.create(p) for p in people]
    background.add_task(pitch.run_queue, ids)
    return {"queued": len(ids), "pitch_ids": ids}


@app.get("/api/people/{pid}/cost")
def person_cost(pid: int, action: str, force: bool = False):
    """What enrich / brief / pitch will spend for this person, shown before the user confirms."""
    guard.person(pid)
    if action == "enrich":
        return costs.enrich(pid)
    if action == "brief":
        return costs.brief(pid, force)
    if action == "pitch":
        return costs.pitches([pid])
    raise HTTPException(400, "action must be enrich, brief or pitch")


@app.post("/api/accounts/{cid}/leadership")
def check_leadership(cid: int):
    """Re-check who holds each top role today from recent sources (about 3 searches and 1 AI call)."""
    guard.company(cid)
    if not (config.TAVILY_API_KEY and llm.available()):
        raise HTTPException(400, "The leadership check needs TAVILY_API_KEY and an AI key")
    from . import people as people_mod
    with db.session() as s:
        company = dict(s.execute("SELECT * FROM company WHERE id=?", (cid,)).fetchone())
    people_mod.merge_duplicates(cid)
    res = people_mod.verify_leadership(company)
    people_mod.refresh_status(cid)
    return res


@app.get("/api/accounts/{cid}/offerings")
def account_offerings(cid: int, refresh: bool = False):
    """Which of your offerings to pitch to this company: 0-100 each, lead / secondary / don't pitch."""
    guard.company(cid)
    if not llm.available():
        raise HTTPException(400, "Ranking offerings needs an AI key")
    return profiles.rank_offerings(cid, refresh)


@app.get("/api/accounts/{cid}/pitches/cost")
def pitch_account_cost(cid: int, limit: int = 5, min_fit: float = 0.5):
    guard.company(cid)
    return costs.pitches(pitch.top_contacts(cid, max(1, min(limit, 25)), min_fit))


class RerunIn(BaseModel):
    ids: list[int]


@app.get("/api/pitches/rerun/cost")
def rerun_cost(ids: str):
    id_list = guard.owned_ids("pitch", [int(x) for x in ids.split(",") if x.strip().isdigit()])
    return costs.pitches(pitch.person_ids(id_list))


@app.post("/api/pitches/rerun")
def rerun_pitches(body: RerunIn, background: BackgroundTasks):
    """Re-write the outreach for these pitches with the current rules, profile and points of view."""
    if not llm.available():
        raise HTTPException(400, "Pitches need OPENAI_API_KEY or ANTHROPIC_API_KEY")
    id_list = guard.owned_ids("pitch", body.ids[:50])
    if not id_list:
        raise HTTPException(400, "Pick at least one pitch")
    new_ids = pitch.rerun(id_list)
    background.add_task(pitch.run_queue, new_ids)
    return {"queued": len(new_ids), "pitch_ids": new_ids}


# ------------------------------------------------------------------ campaigns


class CampaignIn(BaseModel):
    name: str | None = None
    description: str | None = None


class CampaignUrlIn(BaseModel):
    url: str


class FindIn(BaseModel):
    region: str | list[str] | None = None
    days: int = 30
    signals: list[str] | None = None


class CampaignCompany(BaseModel):
    name: str
    domain: str | None = None
    signal: str | None = None
    source_url: str | None = None


class CampaignAccountsIn(BaseModel):
    companies: list[CampaignCompany] = []
    company_ids: list[int] = []      # accounts you already have


def _campaign(cid: int) -> dict:
    try:
        return campaigns.get(cid)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/campaigns")
def list_campaigns():
    return campaigns.list_all()


@app.post("/api/campaigns")
def create_campaign(body: CampaignIn):
    try:
        return campaigns.create(body.name or "", body.description or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/campaigns/{cid}")
def get_campaign(cid: int):
    return _campaign(cid)


@app.put("/api/campaigns/{cid}")
def edit_campaign(cid: int, body: CampaignIn):
    _campaign(cid)
    return campaigns.rename(cid, body.name, body.description)


@app.delete("/api/campaigns/{cid}")
def delete_campaign(cid: int):
    _campaign(cid)
    campaigns.delete(cid)
    return {"deleted": cid}


@app.post("/api/campaigns/{cid}/sources")
async def campaign_sources(cid: int, files: list[UploadFile] = File(...)):
    _campaign(cid)
    added, errors = [], []
    for f in files:
        try:
            added.append(profiles.add_source(f.filename, "deck", profiles.read_file(f.filename, await f.read()), campaign_id=cid))
        except Exception as exc:
            errors.append(f"{f.filename}: {exc}")
    if not added and errors:
        raise HTTPException(400, "; ".join(errors))
    return {"added": added, "errors": errors}


@app.post("/api/campaigns/{cid}/sources/url")
def campaign_source_url(cid: int, body: CampaignUrlIn):
    _campaign(cid)
    if not config.TAVILY_API_KEY:
        raise HTTPException(400, "Reading a page needs TAVILY_API_KEY")
    from .providers import tavily
    try:
        page = tavily.extract(body.url)
        return profiles.add_source(body.url, "web", page["text"][:60_000], body.url, campaign_id=cid)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Couldn't read that page: {config.redact(str(exc))}") from exc


@app.delete("/api/campaigns/{cid}/sources/{sid}")
def campaign_remove_source(cid: int, sid: int):
    _campaign(cid)
    campaigns.remove_source(cid, sid)
    return _campaign(cid)


@app.post("/api/campaigns/{cid}/profile")
def campaign_build_profile(cid: int):
    _campaign(cid)
    if not llm.available():
        raise HTTPException(400, "Building a campaign profile needs an AI key")
    try:
        return campaigns.build_profile(cid)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/campaigns/{cid}/find")
def campaign_find(cid: int, body: FindIn):
    """Companies showing a buying signal for what this campaign's decks sell."""
    _campaign(cid)
    _require_keys()
    try:
        return campaigns.find_companies(cid, body.region, max(1, min(body.days, 365)), body.signals)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/discover/from-decks")
def discover_from_decks(body: FindIn):
    """Companies showing a buying signal for what your general decks sell."""
    _require_keys()
    try:
        return campaigns.find_companies(None, body.region, max(1, min(body.days, 365)), body.signals)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/campaigns/{cid}/accounts")
def campaign_add_accounts(cid: int, body: CampaignAccountsIn, tasks: BackgroundTasks):
    """Put companies in the campaign; new ones are researched one after another."""
    _campaign(cid)
    jobs = []
    for c in body.companies:
        if not c.name.strip():
            continue
        company_id = _upsert_company(c.name, c.domain)
        campaigns.link(cid, company_id, c.signal, c.source_url)
        if not campaigns.researched(company_id) and not db.active_run(company_id):
            jobs.append((_queue_run(company_id), company_id))
    for company_id in body.company_ids:
        guard.company(company_id)
        campaigns.link(cid, company_id)
    if jobs:
        _require_keys()

        def run_all():
            with pipeline.keep_alive([rid for rid, _ in jobs]):
                for run_id, company_id in jobs:
                    pipeline.run(run_id, company_id)
        tasks.add_task(run_all)
    return {"linked": len(body.companies) + len(body.company_ids), "researching": len(jobs), "campaign": _campaign(cid)}


@app.delete("/api/campaigns/{cid}/accounts/{company_id}")
def campaign_remove_account(cid: int, company_id: int):
    _campaign(cid)
    campaigns.unlink(cid, company_id)
    return _campaign(cid)


@app.post("/api/campaigns/{cid}/accounts/{company_id}/pitches")
def campaign_pitch_account(cid: int, company_id: int, body: BulkPitchIn, background: BackgroundTasks):
    """Write this campaign's outreach to the best contacts at one of its companies."""
    camp = _campaign(cid)
    guard.company(company_id)
    if not llm.available():
        raise HTTPException(400, "Pitches need OPENAI_API_KEY or ANTHROPIC_API_KEY")
    if not camp["profile"]:
        raise HTTPException(400, "Build the campaign profile from its decks first")
    people = pitch.top_contacts(company_id, max(1, min(body.limit, 25)), body.min_fit)
    if not people:
        raise HTTPException(400, "No contacts on strong-fit initiatives yet. Wait for research to finish, or lower the fit bar.")
    ids = [pitch.create(p, campaign_id=cid) for p in people]
    background.add_task(pitch.run_queue, ids)
    return {"queued": len(ids), "pitch_ids": ids}


@app.get("/api/pitches.csv")
def pitches_csv(ids: str):
    id_list = guard.owned_ids("pitch", [int(x) for x in ids.split(",") if x.strip().isdigit()])
    return StreamingResponse(iter([pitch.dripify_csv(id_list)]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="dripify_leads.csv"'})


@app.get("/api/accounts/{cid}/export.csv")
def export_csv(cid: int):
    detail = account_detail(cid)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Company", "Initiative", "Category", "Stage", "Fit", "Contact", "Title", "Role", "Score",
                "Why", "Your verdict", "Email", "LinkedIn", "Opener", "Evidence URLs"])
    for i in detail["initiatives"]:
        urls = " | ".join(e["url"] for e in i["evidence"])
        for c in i["contacts"] or [{}]:
            w.writerow([detail["company"]["name"], i["name"], i["category_label"], i["stage"], i["fit_score"],
                        c.get("full_name", ""), c.get("title", ""), c.get("role", ""), c.get("score", ""),
                        c.get("rationale", ""), c.get("feedback") or "", c.get("email") or "", c.get("linkedin_url") or "", c.get("opener", ""), urls])
    w.writerow([])
    w.writerow(["Company", "Project", "Counterparty", "Direction", "Status", "Value", "Fit", "Contact", "Title", "Role",
                "Email", "LinkedIn", "Evidence URLs"])
    for p in detail["projects"]:
        urls = " | ".join(e["url"] for e in p["evidence"])
        for c in p["contacts"] or [{}]:
            w.writerow([detail["company"]["name"], p["name"], p["counterparty"], p["direction"], p["status"], p.get("value") or "",
                        p["fit_score"], c.get("full_name", ""), c.get("title", ""), c.get("role", ""), c.get("email") or "",
                        c.get("linkedin_url") or "", urls])
    buf.seek(0)
    fname = detail["company"]["name"].replace(" ", "_") + "_points_of_contact.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ------------------------------------------------------------------ discover


class RadarIn(BaseModel):
    preset: str | None = None
    query: str | None = None
    region: str | list[str] | None = None
    days: int = 30


class BrowseIn(BaseModel):
    keywords: str | None = None
    location: str | list[str] | None = None
    size: str | None = None
    page: int = 1


@app.get("/api/discover/options")
def discover_options():
    return {"presets": discover.presets(), "sizes": list(discover.SIZES), "locations": discover.location_catalog(),
            **discover.available()}


@app.post("/api/discover/signals")
def discover_signals(body: RadarIn):
    _require_keys()
    try:
        rows = discover.signal_radar(body.preset, body.query, body.region, max(1, min(body.days, 365)))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Signal search failed: {exc}") from exc
    return {"companies": rows}


@app.post("/api/discover/companies")
def discover_companies(body: BrowseIn):
    try:
        return discover.browse(body.keywords, body.location, body.size, max(1, body.page))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


# ------------------------------------------------------------------ frontend
# The React app (frontend-react/dist, prebuilt and shipped in the zip) is served when present;
# otherwise the older plain-HTML frontend in frontend/ is used.

REACT_DIST = config.ROOT / "frontend-react" / "dist"

if (REACT_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=REACT_DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(REACT_DIST / "index.html")
else:
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/")
    def index():
        return FileResponse(Path(FRONTEND) / "index.html")
