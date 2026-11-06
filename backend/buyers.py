"""Buyer briefs: how to approach one person, built only from what they have said publicly.

Runs on demand per contact (it costs a few searches and one LLM call) and is cached for 30 days.
Only professional, public statements are used: interviews, talks, podcasts, articles, public posts.
No guesses about personality, health, family, politics, religion or other personal matters.
"""
import json
from datetime import datetime, timedelta, timezone

from . import db, llm, profiles
from .providers import tavily

CACHE_DAYS = 30

SYSTEM = """You write buyer briefs for B2B sellers from a person's PUBLIC, PROFESSIONAL statements
(interviews, talks, podcasts, articles, public posts, quotes in news).
Only use what the sources show; every point must be traceable to a source. If the sources say little,
say so and keep the brief short. Never speculate about personality disorders, health, family, age,
politics, religion, or anything personal. Describe professional priorities and communication style only."""


def _person(person_id: int) -> dict:
    with db.session() as s:
        row = s.execute(
            """SELECT p.*, c.name company, c.domain FROM person p JOIN company c ON c.id=p.company_id WHERE p.id=?""",
            (person_id,)).fetchone()
    if not row:
        raise LookupError("Person not found")
    return dict(row)


def get(person_id: int) -> dict | None:
    with db.session() as s:
        row = s.execute("SELECT brief, sources, created_at FROM buyer_brief WHERE person_id=?", (person_id,)).fetchone()
    if not row:
        return None
    return {**json.loads(row["brief"]), "created_at": row["created_at"]}


def _fresh(created_at: str) -> bool:
    t = datetime.fromisoformat(created_at).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - t < timedelta(days=CACHE_DAYS)


_ROLE_WORDS = {"cio", "cto", "ceo", "coo", "cfo", "ciso", "cdo", "vp", "svp", "evp", "head", "director", "manager", "lead",
               "chief", "officer", "president", "senior", "sr", "principal", "engineering", "engineer", "technology",
               "information", "digital", "of", "and", "the", "interim", "global", "group", "it", "qa", "quality", "&", "delivery",
               "operations", "product", "products", "sales", "business", "data", "ai", "architect", "program", "programme",
               "practice", "platform", "platforms", "testing", "software", "assurance", "transformation", "strategy"}


def company_aliases(company: str, title: str) -> list[str]:
    """Other names their employer goes by, taken from the title: 'CIO, Carelon Specialty Care' -> ['Carelon Specialty Care']."""
    out = [company]
    for part in re_split(title):
        words = part.split()
        if len(words) >= 2 and any(w[:1].isupper() for w in words) and sum(w.lower().strip(".,") not in _ROLE_WORDS for w in words) >= 1:
            if not all(w.lower().strip(".,") in _ROLE_WORDS for w in words):
                out.append(part.strip())
    first = company.split()[0] if company else ""
    if first and first not in out:
        out.append(first)  # 'Carelon' matches every Carelon unit
    seen, uniq = set(), []
    for a in out:
        if a and a.lower() not in seen:
            seen.add(a.lower())
            uniq.append(a)
    return uniq[:4]


def re_split(title: str) -> list[str]:
    import re
    parts = re.split(r",| at | @ |\||;| - | – ", title or "")
    return [p for p in parts if p.strip()]


# Where people's own words live, by kind. "unscripted" sources (talks, podcasts, comments, forums) show how
# they really speak; "written" ones show how they write; "quoted" ones (press releases, news) are usually
# polished by PR and say little about voice.
SOURCE_FAMILIES = [
    ("profile", "bio", '"{name}" {short}', {}),
    ("talk", "unscripted", '"{name}" keynote OR panel OR webinar OR fireside OR summit OR conference speaker', {}),
    ("podcast", "unscripted", '"{name}" podcast OR episode OR interview', {
        "include_domains": ["youtube.com", "podcasts.apple.com", "open.spotify.com", "buzzsprout.com", "podbean.com",
                            "anchor.fm", "soundcloud.com", "listennotes.com"]}),
    ("interview", "unscripted", '"{name}" {short} interview', {
        "include_domains": ["economictimes.indiatimes.com", "cio.economictimes.indiatimes.com", "cio.com", "analyticsindiamag.com",
                            "yourstory.com", "inc42.com", "forbes.com", "forbesindia.com", "expresscomputer.in", "cxotoday.com",
                            "techcircle.in", "computerweekly.com", "healthcareitnews.com", "finextra.com", "techtarget.com",
                            "zdnet.com", "venturebeat.com", "informationweek.com", "itnext.in", "dqindia.com"]}),
    ("writing", "written", '"{name}"', {
        "include_domains": ["medium.com", "substack.com", "dev.to", "hashnode.dev", "hackernoon.com", "linkedin.com",
                            "slideshare.net", "speakerdeck.com", "quora.com", "x.com", "twitter.com", "github.com"]}),
    ("news", "quoted", '"{name}" said OR says', {"topic": "news", "days": 730}),
]


def search_plan(name: str, company: str, title: str, domain: str | None = None) -> list[tuple]:
    """The web searches a brief runs for this person (also used to estimate its cost)."""
    aliases = company_aliases(company, title)
    short = company.split()[0] if company else ""
    queries = [(fam, voice, tpl.format(name=name, short=short), opts) for fam, voice, tpl, opts in SOURCE_FAMILIES]
    if domain:  # posts, blogs and leadership pages on their own company's site
        queries.append(("company_site", "written", f'"{name}"', {"include_domains": [domain]}))
    for a in [x for x in aliases[1:] if " " in x][:2]:  # specific units named in their title
        queries.append(("profile", "bio", f'"{name}" "{a}"', {}))
    return queries


def needs_rebuild(person_id: int, force: bool = False) -> bool:
    """Would build() search the web again (rather than reuse the saved brief)?"""
    existing = get(person_id)
    return bool(force or not existing or not _fresh(existing["created_at"])
                or existing.get("samples_used", 0) != len(samples(person_id)))


def gather(name: str, company: str, title: str, domain: str | None = None) -> list[dict]:
    """Public pages by or about this person, from many kinds of source, each tagged with its family and voice value."""
    aliases = company_aliases(company, title)
    queries = search_plan(name, company, title, domain)
    full = " ".join(name.lower().split())
    marks = {a.lower() for a in aliases} | {a.lower().split()[0] for a in aliases}
    if domain:
        marks.add(domain.split(".")[0].lower())
    trusted = ("linkedin.com", "youtube.com", "podcasts.apple.com", "open.spotify.com", "x.com", "twitter.com", "medium.com")
    seen, out = set(), []
    for fam, voice, q, opts in queries:
        try:
            results = tavily.raw_search(q, topic=opts.get("topic", "general"), days=opts.get("days"), max_results=5,
                                        include_domains=opts.get("include_domains"), full_text=True)
        except Exception:
            continue
        for r in results:
            blob = " ".join((r["text"] + " " + r["title"]).lower().split())
            # same person: full name, plus any name their employer goes by (personal pages may omit it)
            on_own_site = bool(domain and domain in r["url"])
            if r["url"] in seen or full not in blob or (not any(m in blob for m in marks) and not on_own_site
                                                        and not any(t in r["url"] for t in trusted)):
                continue
            seen.add(r["url"])
            out.append({**r, "family": fam, "voice_value": voice})
    order = {"unscripted": 0, "written": 1, "bio": 2, "quoted": 3}  # most telling first, within the cap
    out.sort(key=lambda r: order.get(r["voice_value"], 9))
    return out[:14]


# ------------------------------------------------------------ pasted samples


def add_sample(person_id: int, text: str, kind: str = "post") -> dict:
    text = (text or "").strip()
    if len(text) < 20:
        raise ValueError("Paste at least a sentence of something they wrote or said")
    _person(person_id)
    with db.session() as s:
        sid = s.execute("INSERT INTO person_sample(person_id, kind, text) VALUES (?,?,?)",
                        (person_id, kind if kind in ("post", "comment", "reply", "article", "talk", "other") else "other",
                         text[:8000])).lastrowid
    return {"id": sid}


def samples(person_id: int) -> list[dict]:
    with db.session() as s:
        return [dict(r) for r in s.execute(
            "SELECT id, kind, text, added_at FROM person_sample WHERE person_id=? ORDER BY id", (person_id,))]


def delete_sample(sample_id: int) -> None:
    with db.session() as s:
        s.execute("DELETE FROM person_sample WHERE id=?", (sample_id,))


def build(person_id: int, force: bool = False) -> dict:
    existing = get(person_id)
    pasted = samples(person_id)
    if existing and not force and _fresh(existing["created_at"]) and existing.get("samples_used", 0) == len(pasted):
        return existing
    p = _person(person_id)
    if "*" in p["full_name"]:
        raise ValueError("This person's surname is hidden. Click Get email first to reveal the full name, then try again.")
    if not llm.available():
        raise ValueError("Buyer briefs need ANTHROPIC_API_KEY or OPENAI_API_KEY")

    sources = gather(p["full_name"], p["company"], p.get("title") or "", p.get("domain"))
    # what you pasted is first-hand by definition, and goes first
    sources = [{"url": "", "title": f"Pasted {x['kind']}", "published_at": (x.get("added_at") or "")[:10], "text": x["text"],
                "pasted": True} for x in pasted] + sources
    seller = profiles.load()
    with db.session() as s:
        roles = [dict(r) for r in s.execute(
            """SELECT i.name, ic.role FROM initiative_contact ic JOIN initiative i ON i.id=ic.initiative_id
               WHERE ic.person_id=?""", (person_id,))]
    kind = {"unscripted": "UNSCRIPTED (talk, podcast, interview: how they really speak)",
            "written": "THEIR WRITING (posts, articles, comments)", "bio": "BIO (about them, not their voice)",
            "quoted": "QUOTED IN NEWS/PRESS (often PR-polished: weak evidence of voice)"}
    listing = "\n\n".join(f"[{i}] {kind.get(r.get('voice_value'), 'THEIR OWN WORDS (pasted by the user)' if r.get('pasted') else 'OTHER')} | "
                          f"{r['title']} ({r.get('published_at') or 'undated'})\n{r['url'] or 'pasted by the user'}\n{r['text'][:2200]}"
                          for i, r in enumerate(sources)) or "(no public statements found)"
    prompt = f"""Person: {p['full_name']}, {p.get('title') or 'title unknown'} at {p['company']}
Their initiatives in our research: {json.dumps(roles) if roles else 'none linked'}
We sell: {seller.get('description', '')} Offerings: {', '.join(o['name'] for o in seller.get('offerings', []))}

Public sources:
{listing}

Every point is an object {{"text": ..., "source": source number it comes from, or null if it is only typical
for someone in this role}}. Prefer points with a source; add role-typical points only to fill gaps, and never
present a role-typical point as something they said.

Return {{
"summary": 2 sentences on who they are professionally and what they focus on,
"topics": [{{"topic": what they spoke or wrote about, "quote": their exact words (short), "source": n, "date": date if known}}]
          (only things THEY said or wrote, first-hand; empty if none),
"priorities": [3-5 points], "motivators": [points: what they want to achieve], "concerns": [points: risks or frustrations],
"communication_style": one of ["data-driven","visionary","pragmatic","technical","relationship-led","unknown"],
"style_note": one sentence explaining the style from the sources,
"approach": [3 points: specific ways to open a conversation], "avoid": [points: things that would put them off; only with a source, else empty],
"talking_points": [2-3 points linking their priorities to what we sell],
"evidence": [{{"source": source number, "quote": exact short quote}}],
"first_hand": number of sources where they speak or write themselves,
"voice": {{  // HOW they communicate, judged ONLY from words they wrote or said themselves. Weigh UNSCRIPTED sources and
           // pasted text most, THEIR WRITING next; a press-release quote alone is not enough to judge voice
  "samples": number of first-hand texts this is based on (0 if none),
  "register": "formal" | "neutral" | "casual",
  "length": "terse" | "short" | "medium" | "long" (how much they typically write),
  "directness": "blunt" | "direct" | "diplomatic",
  "evidence": "numbers" | "stories" | "opinions" | "mixed" (how they make a point),
  "energy": "reserved" | "measured" | "enthusiastic",
  "vocabulary": [words or phrases they actually use, verbatim, up to 8],
  "emoji_hashtags": "never" | "sometimes" | "often",
  "how_they_reply": how they respond to others (asks questions back, one-liners, thanks people, debates, etc.) or null,
  "they_engage_with": [kinds of posts or ideas they respond to],
  "summary": one sentence a salesperson can act on,
  "mirror": [3-5 concrete rules for writing to them, e.g. "two sentences max", "lead with a number", "no exclamation marks"],
  "avoid": [2-3 tone mistakes that would put them off]
}}  // if there are no first-hand texts, set samples 0 and give only cautious role-based defaults in mirror,
"confidence": "high" if 3+ first-hand sources, "medium" if 1-2, "low" if none
}}"""
    brief = llm.complete_json(SYSTEM, prompt, 2500)
    if not isinstance(brief, dict):
        raise RuntimeError("The AI did not return a brief")
    brief["sources"] = [{"n": i, "url": r["url"], "title": r["title"], "published_at": r.get("published_at"),
                         "pasted": bool(r.get("pasted")), "family": r.get("family") or ("pasted" if r.get("pasted") else None),
                         "voice_value": r.get("voice_value")} for i, r in enumerate(sources)]
    brief["samples_used"] = len(pasted)
    if not isinstance(brief.get("voice"), dict):
        brief["voice"] = {"samples": 0}
    if not pasted and not brief.get("first_hand"):
        brief["voice"]["samples"] = 0
    if not sources:
        brief["confidence"] = "low"
        brief["note"] = "No public statements found. Tips are based on the role only."
    with db.session() as s:
        s.execute("INSERT OR REPLACE INTO buyer_brief(person_id, brief, sources, created_at) VALUES (?,?,?,CURRENT_TIMESTAMP)",
                  (person_id, json.dumps(brief), len(sources)))
    return get(person_id)
