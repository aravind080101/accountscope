"""Campaigns: a named group of decks and documents with its own profile, company search and outreach.

A campaign's decks never mix with the general library. Pitches written inside a campaign use only that
campaign's offerings, proof, offers and deck passages (the seller's name, voice and leadership points of view
still come from the general profile).

Finding companies from decks works for a campaign or for the general library: the AI reads the material and
turns it into a few buying-signal searches (who would need this right now), which run through the signal radar.
"""
import json

from . import db, discover, llm, profiles, tenancy

CAMPAIGN_PROFILE_SYSTEM = """You turn one sales campaign's decks and documents into a focused profile: what this campaign
sells, to whom, with what proof, and what a company would be doing in the news or job posts right now that means it
needs this. Use only the material. Never invent clients, numbers or offerings."""

SEARCH_SYSTEM = """You plan company searches for a seller. From what they sell and who buys it, write news/job-post
search queries that find companies showing a buying signal RIGHT NOW (launching, migrating, hiring, rolling out,
being fined, expanding). Each query names the activity, not the seller. Short, search-engine style."""


# ------------------------------------------------------------------ CRUD


def create(name: str, description: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Give the campaign a name")
    with db.session() as s:
        cid = s.execute("INSERT INTO campaign(workspace_id, name, description) VALUES (?,?,?)",
                        (tenancy.current(), name[:120], (description or "").strip()[:1000])).lastrowid
    return get(cid)


def _row(cid: int) -> dict | None:
    with db.session() as s:
        r = s.execute("SELECT * FROM campaign WHERE id=? AND workspace_id=?", (cid, tenancy.current())).fetchone()
    return dict(r) if r else None


def get(cid: int) -> dict:
    r = _row(cid)
    if not r:
        raise LookupError("Campaign not found")
    r["profile"] = json.loads(r["profile"]) if r.get("profile") else None
    with db.session() as s:
        r["sources"] = [dict(x) for x in s.execute(
            "SELECT id, name, kind, url, LENGTH(text) chars, added_at FROM seller_doc WHERE campaign_id=? ORDER BY added_at DESC", (cid,))]
        r["accounts"] = [dict(x) for x in s.execute(
            """SELECT c.id company_id, c.name, c.domain, c.industry, c.hq_country, ca.signal, ca.source_url, ca.added_at,
                      (SELECT status FROM run WHERE company_id=c.id ORDER BY id DESC LIMIT 1) status,
                      (SELECT COUNT(*) FROM pitch pt JOIN person p ON p.id=pt.person_id
                         WHERE p.company_id=c.id AND pt.campaign_id=ca.campaign_id) pitches
               FROM campaign_account ca JOIN company c ON c.id=ca.company_id WHERE ca.campaign_id=? ORDER BY ca.added_at DESC""",
            (cid,))]
    return r


def list_all() -> list[dict]:
    with db.session() as s:
        return [dict(r) for r in s.execute(
            """SELECT cp.id, cp.name, cp.description, cp.profile IS NOT NULL has_profile, cp.created_at,
                      (SELECT COUNT(*) FROM seller_doc d WHERE d.campaign_id=cp.id) docs,
                      (SELECT COUNT(*) FROM campaign_account a WHERE a.campaign_id=cp.id) accounts,
                      (SELECT COUNT(*) FROM pitch pt WHERE pt.campaign_id=cp.id) pitches
               FROM campaign cp WHERE cp.workspace_id=? ORDER BY cp.created_at DESC""", (tenancy.current(),))]


def rename(cid: int, name: str | None, description: str | None) -> dict:
    if not _row(cid):
        raise LookupError("Campaign not found")
    with db.session() as s:
        if name and name.strip():
            s.execute("UPDATE campaign SET name=? WHERE id=?", (name.strip()[:120], cid))
        if description is not None:
            s.execute("UPDATE campaign SET description=? WHERE id=?", (description.strip()[:1000], cid))
    return get(cid)


def delete(cid: int) -> None:
    """Remove the campaign and its documents. Researched companies and written pitches stay (pitches become general)."""
    if not _row(cid):
        raise LookupError("Campaign not found")
    with db.session() as s:
        s.execute("DELETE FROM seller_doc WHERE campaign_id=?", (cid,))
        s.execute("DELETE FROM campaign_account WHERE campaign_id=?", (cid,))
        s.execute("UPDATE pitch SET campaign_id=NULL WHERE campaign_id=?", (cid,))
        s.execute("DELETE FROM campaign WHERE id=?", (cid,))


def owns(cid: int) -> bool:
    return _row(cid) is not None


def remove_source(cid: int, sid: int) -> None:
    with db.session() as s:
        s.execute("DELETE FROM seller_doc WHERE id=? AND campaign_id=? AND workspace_id=?", (sid, cid, tenancy.current()))


# ------------------------------------------------------------------ campaign profile


def _material(cid: int) -> str:
    with db.session() as s:
        docs = [dict(r) for r in s.execute("SELECT name, text FROM seller_doc WHERE campaign_id=? ORDER BY added_at DESC", (cid,))]
    if not docs:
        return ""
    per = max(4000, 80_000 // len(docs))
    return "\n\n".join(f"### {d['name']}\n{d['text'][:per]}" for d in docs)[:80_000]


def build_profile(cid: int) -> dict:
    camp = _row(cid)
    if not camp:
        raise LookupError("Campaign not found")
    material = _material(cid)
    if not material:
        raise ValueError("Add this campaign's decks or documents first")
    out = llm.complete_json(CAMPAIGN_PROFILE_SYSTEM, f"""Campaign: {camp['name']}
Notes from the user: {camp.get('description') or 'none'}

MATERIAL:
{material}

Return JSON {{"description": "2 sentences: what this campaign sells and to whom",
"offerings": [{{"name": short name, "kind": "service" or "product", "what": one sentence,
  "problems": [3-6 situations at a target company that create demand for it], "buyers": [3-5 job titles]}}],
"proof": [named clients, case-study results and numbers from the material],
"offers": [{{"name": short name, "what": a concrete give-first or entry offer the material supports, "for": who it suits,
  "effort_for_them": what the buyer has to give}}],
"buyer_titles": [4-8 titles that buy this],
"target_industries": [industries this campaign is for],
"target_regions": [countries or regions named, or []],
"search_signals": [4-6 short news/job-post search queries for companies that need this NOW, e.g.
  "bank announces core banking migration", "insurer launches customer app"],
"search_keywords": [4-8 industry keywords for a company database search]}}""", 3500)
    if not out.get("offerings"):
        raise ValueError("Couldn't find what this campaign sells in those documents")
    with db.session() as s:
        s.execute("UPDATE campaign SET profile=? WHERE id=?", (json.dumps(out), cid))
    return get(cid)


def profile_for(cid: int) -> dict:
    """The seller profile used for this campaign's pitches: the general identity (name, voice, leadership POV)
    with this campaign's offerings, proof, offers and buyers."""
    base = profiles.load()
    camp = get(cid)
    p = camp["profile"] or {}
    if not p:
        raise ValueError(f"Build the '{camp['name']}' campaign profile from its decks first")
    return {**base,
            "description": p.get("description") or base.get("description"),
            "offerings": p.get("offerings") or [],
            "proof": p.get("proof") or [],
            "offers": p.get("offers") or base.get("offers") or [],
            "buyer_titles": p.get("buyer_titles") or base.get("buyer_titles") or [],
            "campaign": {"id": cid, "name": camp["name"]}}


# ------------------------------------------------------------------ find companies from decks


def search_plan(cid: int | None) -> dict:
    """Signal queries and keywords to find companies that need what the decks sell."""
    if cid:
        p = get(cid)["profile"]
        if not p:
            raise ValueError("Build the campaign profile from its decks first")
        if p.get("search_signals"):
            return {"signals": p["search_signals"][:6], "keywords": p.get("search_keywords") or [],
                    "regions": p.get("target_regions") or []}
        profile = p
    else:
        profile = profiles.load()
        if not profile.get("offerings"):
            raise ValueError("Build your profile from your decks first (What you sell)")
    from . import cache
    key = f"deck_search:{tenancy.current()}:{cid or 0}:{hash(json.dumps(profile.get('offerings'), sort_keys=True))}"
    hit = cache.get(key, 24 * 14)
    if hit:
        return hit
    out = llm.complete_json(SEARCH_SYSTEM, f"""WHAT THEY SELL:
{json.dumps(profile.get('offerings'), indent=1)[:6000]}
Buyers: {profile.get('buyer_titles')}
Industries: {profile.get('target_industries') or 'any'}

Return {{"signals": [4-6 news/job-post search queries], "keywords": [4-8 industry keywords]}}""", 800)
    plan = {"signals": [str(x) for x in (out.get("signals") or [])][:6], "keywords": [str(x) for x in (out.get("keywords") or [])][:8],
            "regions": profile.get("target_regions") or []}
    cache.put(key, plan)
    return plan


def find_companies(cid: int | None, region=None, days: int = 30, signals: list[str] | None = None, max_queries: int = 3) -> dict:
    """Run the deck-derived searches through the signal radar and merge the results."""
    plan = search_plan(cid)
    queries = [q for q in (signals or plan["signals"]) if q][:max_queries]
    if not queries:
        raise ValueError("No searches could be planned from these documents")
    linked = set()
    if cid:
        with db.session() as s:
            linked = {r["company_id"] for r in s.execute("SELECT company_id FROM campaign_account WHERE campaign_id=?", (cid,))}
    rows, seen = [], {}
    for q in queries:
        try:
            hits = discover.signal_radar(None, q, region, days)
        except Exception:
            continue
        for h in hits:
            k = h["name"].lower()
            if k in seen:
                seen[k]["matched"].append(q)
                continue
            h["matched"] = [q]
            h["in_campaign"] = bool(h.get("account_id") and h["account_id"] in linked)
            seen[k] = h
            rows.append(h)
    rows.sort(key=lambda h: -len(h["matched"]))
    return {"companies": rows, "plan": plan, "queries": queries}


def link(cid: int, company_id: int, signal: str | None = None, source_url: str | None = None) -> None:
    """Put a company in the campaign (keeps the first reason it was picked unless a new one is given)."""
    with db.session() as s:
        s.execute("""INSERT INTO campaign_account(campaign_id, company_id, signal, source_url) VALUES (?,?,?,?)
                     ON CONFLICT(campaign_id, company_id) DO UPDATE SET signal=COALESCE(excluded.signal, signal),
                     source_url=COALESCE(excluded.source_url, source_url)""", (cid, company_id, signal, source_url))


def researched(company_id: int) -> bool:
    with db.session() as s:
        return bool(s.execute("SELECT 1 FROM run WHERE company_id=? AND status='done'", (company_id,)).fetchone())


def unlink(cid: int, company_id: int) -> None:
    with db.session() as s:
        s.execute("DELETE FROM campaign_account WHERE campaign_id=? AND company_id=?", (cid, company_id))
