"""The seller's profile: what this workspace sells, used to judge fit and pick buyers.

Nothing here is keyword- or category-based. The profile is free text built from the
seller's own material (uploaded decks, their website and public pages found with Tavily),
and fit is judged by the AI reading each initiative against that material.

Moolya (QA services) + Bugasura (its agentic QA product) is the seed profile, written from
public sources in Nov 2026. Rebuild it from your decks in Settings.
"""
import io
import json
from pathlib import Path

from . import config, db, llm, tenancy

PROFILE_PATH = Path(config.DB_PATH).parent / "profile.json"

MOOLYA_PROFILE = {
    "company": "Moolya",
    "description": (
        "Moolya (Bengaluru, since 2010, ~500 people) is a software testing company that prevents bugs and tech "
        "debt for fast-growing startups and enterprises, bringing a product-owner mindset to testing. Its sister "
        "product Bugasura is a customer-focused agentic QA platform (test management, AI bug tracking, QA agents)."
    ),
    "offerings": [
        {
            "name": "Managed QA & exploratory testing",
            "kind": "service",
            "what": "Dedicated QA/SDET teams and managed testing using context-driven, exploratory testing with a PO/BA mindset; staff augmentation or fully managed.",
            "problems": ["releases slipping bugs to users", "no in-house QA team or QA can't keep up with dev speed",
                         "large transformation programmes needing an independent quality gate"],
            "buyers": ["CTO", "VP Engineering", "Head of QA", "Director Quality Engineering"],
        },
        {
            "name": "Test automation & SDET",
            "kind": "service",
            "what": "Automation frameworks and suites for web, mobile and API (Selenium, Playwright, Appium, API testing), integrated with CI/CD.",
            "problems": ["slow manual regression", "flaky or missing automation", "scaling releases without scaling headcount"],
            "buyers": ["Head of QA", "Engineering Manager", "VP Engineering"],
        },
        {
            "name": "Mobile, OTT & device testing",
            "kind": "service",
            "what": "Cross-platform testing on Android, iOS, wearables, smart TVs and streaming devices.",
            "problems": ["app launches or redesigns", "fragmented device coverage", "streaming/OTT playback quality"],
            "buyers": ["Head of Mobile", "Product Head", "Head of QA"],
        },
        {
            "name": "Performance, security & accessibility testing",
            "kind": "service",
            "what": "Load/performance testing, security functional testing and accessibility audits.",
            "problems": ["scale events and peak traffic", "cloud or platform migrations", "compliance and security audits",
                         "accessibility obligations"],
            "buyers": ["CTO", "CISO", "Head of Platform", "Head of QA"],
        },
        {
            "name": "Testing AI systems",
            "kind": "service",
            "what": "Testing GenAI and agentic features: evaluation, hallucination and safety checks, regression for LLM apps.",
            "problems": ["shipping chatbots, copilots or agents to customers", "no way to evaluate AI quality before rollout"],
            "buyers": ["Head of AI", "CTO", "Product Head"],
        },
        {
            "name": "Quality consulting & data testing",
            "kind": "service",
            "what": "QA strategy, process and culture change; data/ETL testing; UI/UX and white-box testing.",
            "problems": ["quality culture and process problems during growth", "data platform builds and migrations"],
            "buyers": ["CTO", "VP Engineering", "Head of Data"],
        },
        {
            "name": "Bugasura (agentic QA platform)",
            "kind": "product",
            "what": "Free test management and AI bug tracking; Testpert expert AI test design; Asura agents (browser, API, mobile, duplicate-bug); Eagle Eye release-readiness view for leaders; MCP server for Claude/Cursor; SOC 2 Type II, on-prem, SSO.",
            "problems": ["replacing or consolidating a bug tracker / test management tool", "teams adopting AI coding tools whose QA lags",
                         "leaders lacking release-readiness visibility"],
            "buyers": ["Head of QA", "Engineering Manager", "VP Engineering", "CTO"],
        },
    ],
    "proof": [
        "Clients and testimonials include PhonePe, Tesco, Rabobank (banking transformation), NBC Universal, Zeotap, Mindtickle, Flipkart, Myntra, Tata CLiQ",
        "200+ customer stories; Bugasura used by 50,000+ engineers in 25 countries (Godrej, NTT, Trigent)",
    ],
    # Give-first offers the pitch agent may use. DRAFTS: edit to match what Moolya will actually do.
    "offers": [
        {"name": "Release-risk review", "what": "A 45-minute session on one upcoming release or migration: top risks and a test-plan outline they keep.",
         "for": "migrations, platform rebuilds, big launches", "effort_for_them": "45 minutes"},
        {"name": "Two-week testing pilot", "what": "A Moolya team tests one app or module for two weeks; findings shared either way.",
         "for": "teams short on QA capacity or about to release", "effort_for_them": "access to one build"},
        {"name": "Real-device check", "what": "Their app run on real phones, TVs and streaming devices; a short report of device-specific issues.",
         "for": "mobile, OTT and consumer apps", "effort_for_them": "an app build or store link"},
        {"name": "GenAI feature evaluation", "what": "An evaluation of one AI feature (chatbot, copilot, agent) for wrong answers, unsafe output and regressions.",
         "for": "companies shipping GenAI to customers", "effort_for_them": "test access to the feature"},
        {"name": "Bugasura workspace + Testpert walkthrough", "what": "Free Bugasura workspace and a walkthrough of AI test design on their own user stories.",
         "for": "QA leads replacing tools or adopting AI in testing", "effort_for_them": "30 minutes"},
        {"name": "Community invite", "what": "Invite to a Moolya practitioner event (e.g. 'Testing AI' meetups in Bengaluru, TribeQonf).",
         "for": "QA and engineering leaders who speak or post publicly", "effort_for_them": "an evening"},
    ],
    "buyer_titles": ["Head of QA", "Director Quality Engineering", "QA Manager", "Head of Testing", "VP Quality", "VP Engineering"],
    "competitors": [],
    "sources": [{"name": "moolya.com, bugasura.io and public profiles (seed)", "kind": "web"}],
}


def blank(company: str) -> dict:
    """A new workspace starts empty: its team adds decks and runs the web research to fill it."""
    return {"company": company, "description": "", "offerings": [], "offers": [], "proof": [],
            "buyer_titles": [], "competitors": [], "sources": []}


def legacy_company_name() -> str | None:
    """Seller name from a profile.json saved before workspaces existed."""
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text()).get("company")
        except Exception:
            return None
    return None


def _legacy_file_profile() -> dict | None:
    if not PROFILE_PATH.exists():
        return None
    p = json.loads(PROFILE_PATH.read_text())
    # the old keyword-based seed is replaced by the researched one
    if p.get("company") == "Moolya" and any("keywords" in o for o in p.get("offerings", [])):
        return dict(MOOLYA_PROFILE)
    if "offers" not in p and p.get("company") == "Moolya":
        p["offers"] = MOOLYA_PROFILE["offers"]
    return p


def load(workspace_id: int | None = None) -> dict:
    wid = workspace_id or tenancy.current()
    with db.session() as s:
        row = s.execute("SELECT name, profile FROM workspace WHERE id=?", (wid,)).fetchone()
    if row and row["profile"]:
        return json.loads(row["profile"])
    if wid == 1:  # the first workspace keeps what was set up before workspaces existed, else the Moolya seed
        return _legacy_file_profile() or dict(MOOLYA_PROFILE)
    return blank(row["name"] if row else "")


def save(profile: dict, workspace_id: int | None = None) -> dict:
    wid = workspace_id or tenancy.current()
    with db.session() as s:
        s.execute("UPDATE workspace SET profile=? WHERE id=?", (json.dumps(profile), wid))
    return profile


# ------------------------------------------------------------ seller material


def read_file(filename: str, data: bytes) -> str:
    """Text from a deck or document: PDF, PowerPoint, Word, or plain text."""
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".pptx"):
        from pptx import Presentation
        out = []
        for n, slide in enumerate(Presentation(io.BytesIO(data)).slides, 1):
            bits = [sh.text_frame.text for sh in slide.shapes if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip()]
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
                bits.append("Notes: " + slide.notes_slide.notes_text_frame.text)
            out.append(f"[Slide {n}] " + "\n".join(bits))
        return "\n\n".join(out)
    if name.endswith(".docx"):
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    if name.endswith((".txt", ".md", ".csv")):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Upload a PDF, PowerPoint (.pptx), Word (.docx) or text file. Save .ppt/.key decks as PDF first.")


def add_source(name: str, kind: str, text: str, url: str | None = None) -> dict:
    text = (text or "").strip()
    if len(text) < 50:
        raise ValueError(f"Couldn't read any text from {name}. If it's a scanned or image-only deck, export it with text.")
    with db.session() as s:
        wid = tenancy.current()
        s.execute("DELETE FROM seller_doc WHERE workspace_id=? AND name=? AND kind=?", (wid, name, kind))
        cur = s.execute("INSERT INTO seller_doc(workspace_id, name, kind, url, text) VALUES (?,?,?,?,?)",
                        (wid, name, kind, url, text[:200_000]))
        return {"id": cur.lastrowid, "name": name, "kind": kind, "chars": len(text)}


def list_sources() -> list[dict]:
    with db.session() as s:
        return [dict(r) for r in s.execute(
            "SELECT id, name, kind, url, LENGTH(text) chars, added_at FROM seller_doc WHERE workspace_id=? ORDER BY kind, added_at DESC",
            (tenancy.current(),))]


def delete_source(sid: int) -> None:
    with db.session() as s:
        s.execute("DELETE FROM seller_doc WHERE id=? AND workspace_id=?", (sid, tenancy.current()))


def research_web(targets: list[dict]) -> list[dict]:
    """Tavily: read the seller's own sites plus public pages about each of their companies/products."""
    from .providers import tavily
    added = []
    for t in targets:
        name, domain = t["name"].strip(), (t.get("domain") or "").strip() or None
        queries = []
        if domain:
            queries += [(f"{name} services products solutions", [domain]), (f"{name} case study customers", [domain]),
                        (f"{name} pricing features platform", [domain])]
        queries += [(f"{name} software testing company services clients", None), (f"{name} reviews customers", None)]
        for q, domains in queries:
            try:
                results = tavily.raw_search(q, max_results=6, include_domains=domains, full_text=True)
            except Exception:
                continue
            for r in results:
                text = r.get("text") or ""
                if len(text) > 200:
                    try:
                        added.append(add_source(r.get("title") or r["url"], "web", text[:30_000], r["url"]))
                    except ValueError:
                        pass
    return added


def _material(limit: int = 90_000) -> str:
    docs = []
    with db.session() as s:
        docs = [dict(r) for r in s.execute("SELECT name, kind, text FROM seller_doc WHERE workspace_id=? ORDER BY kind='web', added_at DESC",
                                           (tenancy.current(),))]
    if not docs:
        return ""
    per = max(3000, limit // len(docs))  # decks first, each gets a fair share
    return "\n\n".join(f"### {d['kind'].upper()}: {d['name']}\n{d['text'][:per]}" for d in docs)[:limit]


PROFILE_SYSTEM = """You configure a B2B account-intelligence tool for the seller described in the material.
Read the seller's own decks and web pages and describe what they actually sell, in their terms.
Do not squeeze offerings into generic categories. Keep product and service offerings separate.
Only state things the material supports."""


def build(company: str = "", extra: str = "") -> dict:
    """Write the profile from every deck and web page added. Keeps hand-entered competitors."""
    material = _material()
    if not material and not extra:
        raise ValueError("Add a deck or run the web research first")
    old = load()
    prompt = f"""Seller name (if given): {company or old.get('company', '')}
Extra notes from the user: {extra or 'none'}

MATERIAL:
{material}

Return JSON {{"company": str, "description": "2-3 sentences",
"offerings": [{{"name": short name the seller uses, "kind": "service" or "product",
  "what": one sentence on what it is, "problems": [3-6 situations at a target company that create demand for it],
  "buyers": [3-5 job titles who buy it]}}],
"proof": [named clients, case-study results and numbers from the material],
"offers": [{{"name": short name, "what": a concrete give-first or entry offer the material supports (assessment, pilot, workshop,
  free tool, trial, event), "for": who or what situation it suits, "effort_for_them": what the buyer has to give}}],
"buyer_titles": [4-8 titles that buy from this seller overall],
"competitors": [firms the material names or that clearly sell the same thing]}}.
List every distinct offering in the material, typically 4-12."""
    p = llm.complete_json(PROFILE_SYSTEM, prompt, 4000)
    if not p.get("offerings"):
        raise ValueError("The AI didn't return any offerings; try again or add more material")
    p["competitors"] = sorted(set(p.get("competitors") or []) | set(old.get("competitors") or []))
    if not p.get("offers"):
        p["offers"] = old.get("offers", [])
    p["sources"] = [{"name": d["name"], "kind": d["kind"]} for d in list_sources()]
    return save(p)


def from_description(company: str, description: str) -> dict:
    """Quick start without decks: the AI drafts a profile from a sentence plus any added material."""
    return build(company, description)


# ------------------------------------------------------------------- fit


def _offerings_text(profile: dict) -> str:
    lines = []
    for n, o in enumerate(profile.get("offerings", []), 1):
        bits = [o.get("what", "")]
        if o.get("problems"):
            bits.append("demand when: " + "; ".join(o["problems"]))
        lines.append(f"{n}. {o['name']} ({o.get('kind', 'service')}): " + " | ".join(b for b in bits if b))
    return "\n".join(lines)


FIT_SYSTEM = """You judge sales fit for a seller. For each initiative at the target company, decide whether
the seller could credibly help with it now, and with which offering. Judge the actual work, not word overlap:
an AI chatbot launch needs AI testing; a bank's core migration needs regression and performance testing;
a hiring push for QA engineers means they need QA capacity. Be strict: unrelated initiatives score below 30."""


def fit_many(profile: dict, company: dict, inits: list[dict]) -> list[tuple[float, str]]:
    """[(score 0-1, 'Offering: reason')] for each initiative, judged by the AI in one call."""
    if not inits:
        return []
    if not llm.available():
        return [(0.0, "Fit needs an AI key")] * len(inits)
    if not profile.get("offerings"):
        return [(0.0, "Set up What you sell to score fit")] * len(inits)
    listing = "\n".join(
        f"{n}. {i['name']} [stage: {i.get('stage')}] {i.get('summary', '')} Tech: {', '.join(i.get('tech', [])[:8])}"
        for n, i in enumerate(inits))
    prompt = f"""Seller: {profile.get('company')}. {profile.get('description', '')}
Offerings:
{_offerings_text(profile)}

Target company: {company.get('name')} ({company.get('industry') or 'industry unknown'})
Initiatives:
{listing}

Return {{"fits": [{{"n": initiative number, "score": 0-100, "offering": exact offering name or "",
"reason": one sentence a salesperson can use, naming the concrete need}}]}} with one entry per initiative."""
    try:
        out = llm.complete_json(FIT_SYSTEM, prompt, 2500).get("fits") or []
    except Exception as exc:
        return [(0.0, f"Fit check failed: {exc}")] * len(inits)
    res = [(0.0, "Not judged")] * len(inits)
    for f in out:
        try:
            n = int(f.get("n"))
            score = max(0.0, min(float(f.get("score", 0)) / 100, 1.0))
        except (TypeError, ValueError):
            continue
        if 0 <= n < len(inits):
            offer = (f.get("offering") or "").strip()
            reason = (f.get("reason") or "").strip()
            res[n] = (round(score, 2), f"{offer}: {reason}" if offer else (reason or "No offering fits"))
    return res


def rescore_company(company_id: int) -> int:
    """Re-judge fit for a company's saved initiatives without re-researching it."""
    profile = load(tenancy.of_company(company_id))
    with db.session() as s:
        company = dict(s.execute("SELECT * FROM company WHERE id=?", (company_id,)).fetchone())
        inits = [dict(r) for r in s.execute("SELECT * FROM initiative WHERE company_id=?", (company_id,))]
    for i in inits:
        i["tech"] = json.loads(i.get("tech") or "[]")
    fits = fit_many(profile, company, inits)
    with db.session() as s:
        for i, (score, reason) in zip(inits, fits):
            s.execute("UPDATE initiative SET fit_score=?, fit_reason=? WHERE id=?", (score, reason, i["id"]))
        projs = [dict(r) for r in s.execute("SELECT * FROM project WHERE company_id=?", (company_id,))]
    if projs:
        pf = fit_many(profile, company, [
            {"name": f"{p['name']} ({'for client' if p['direction'] == 'client' else 'delivered by partner'} {p['counterparty']})",
             "summary": p.get("summary") or "", "tech": json.loads(p.get("tech") or "[]"), "stage": p.get("status")} for p in projs])
        with db.session() as s:
            for p, (score, reason) in zip(projs, pf):
                s.execute("UPDATE project SET fit_score=?, fit_reason=? WHERE id=?", (score, reason, p["id"]))
    return len(inits) + len(projs)
