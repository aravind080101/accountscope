"""Pitch agent: turns one contact into a Dripify-ready sequence that has a real technical hook.

Agents, in order (each logs a step the UI shows):
  1. Researcher  - what this person has said publicly (buyer brief), plus what we know about their
                   company: the initiatives and projects they're linked to, tech, vendors, competitors.
  2. Trigger     - what actually hits this person: a pain they voiced, a public commitment or deadline,
     finder        an ambition, a fresh event, a peer or competitor move. Plus a pre-mortem: why they'd
                   ignore a vendor at all.
  3. Strategist  - finds angles where THEIR words or THEIR company's work meet what we sell, adds the
                   technical insight an expert tester would raise, and picks one give-first offer.
  4. Hooks       - six opening lines in different styles; the simulated person sees only the LinkedIn
                   preview and picks the one that would make them stop scrolling.
  5. Writer      - writes the connection note (opening on the winning hook), three follow-ups and an email.
  4. Buyer       - plays the person (skeptical, busy, gets 30 vendor messages a week), reacts to each
     simulator     message, scores it and says what would make them ignore or refute it.
  5. Loop        - the writer revises from that critique until the simulated buyer would accept and
                   reply (score >= PASS_SCORE), switching to the next angle if one keeps failing.
  6. Objections  - likely push-backs ("we have in-house QA", "send a deck") with ready replies.

Nothing is sent automatically. Pitches are reviewed, edited and exported as a CSV for Dripify.
"""
import json
import os
import re

from . import buyers, config, db, llm, profiles, tenancy

PASS_SCORE = 7.5
MAX_ROUNDS = 4
LIMITS = {
    "connection_note": int(os.getenv("CONNECTION_NOTE_MAX", "280")),  # LinkedIn: 300 with Premium, 200 on free accounts
    "message_1": 500,
}
# First touches never ask for time. The goal is a reply, not a meeting.
TIME_ASK = re.compile(r"\b\d+\s*-?\s*min(ute)?s?\b|\b(call|meeting|demo|calendar|calendly|schedule|slot|hop on|jump on|catch up|"
                      r"chat this week|book a|set up a time|free next week|available (this|next) week)\b", re.I)
BANNED = ["hope this finds you", "i came across your profile", "i'd love to connect", "synergy", "leverage", "cutting-edge",
          "world-class", "best-in-class", "game-changer", "seamless", "robust solution", "touch base", "quick call",
          "reach out", "pick your brain", "revolutionize", "end-to-end solutions", "one-stop"]


# ------------------------------------------------------------------ storage


def _log(pid: int, msg: str) -> None:
    with db.session() as s:
        row = s.execute("SELECT log FROM pitch WHERE id=?", (pid,)).fetchone()
        log = json.loads(row["log"] or "[]") + [config.redact(msg)]
        s.execute("UPDATE pitch SET log=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(log), pid))


def create(person_id: int, kind: str | None = None, context_id: int | None = None) -> int:
    with db.session() as s:
        if not s.execute("SELECT 1 FROM person WHERE id=?", (person_id,)).fetchone():
            raise LookupError("Person not found")
        s.execute("DELETE FROM pitch WHERE person_id=? AND status IN ('ready','failed','running','queued')", (person_id,))
        return s.execute("INSERT INTO pitch(person_id, context_kind, context_id, status, log) VALUES (?,?,?, 'queued', '[]')",
                         (person_id, kind, context_id)).lastrowid


def get(pitch_id: int) -> dict | None:
    with db.session() as s:
        r = s.execute(
            """SELECT pt.*, p.full_name, p.title, p.linkedin_url, p.email, p.email, c.name company, c.id company_id FROM pitch pt
               JOIN person p ON p.id=pt.person_id JOIN company c ON c.id=p.company_id WHERE pt.id=?""", (pitch_id,)).fetchone()
    if not r:
        return None
    out = dict(r)
    out["log"] = json.loads(out["log"] or "[]")
    out["data"] = json.loads(out["data"] or "{}")
    return out


def latest_for_person(person_id: int) -> dict | None:
    with db.session() as s:
        r = s.execute("SELECT id FROM pitch WHERE person_id=? ORDER BY id DESC LIMIT 1", (person_id,)).fetchone()
    return get(r["id"]) if r else None


def list_all(company_id: int | None = None, workspace_id: int | None = None) -> list[dict]:
    q = """SELECT pt.id, pt.person_id, pt.status, pt.score, pt.updated_at, pt.data, p.full_name, p.title, p.linkedin_url, p.email,
           c.name company, c.id company_id FROM pitch pt JOIN person p ON p.id=pt.person_id JOIN company c ON c.id=p.company_id
           WHERE c.workspace_id=?"""
    args: tuple = (workspace_id or tenancy.current(),)
    if company_id:
        q += " AND c.id=?"
        args = args + (company_id,)
    with db.session() as s:
        rows = db.rows(s.execute(q + " ORDER BY pt.updated_at DESC", args))
    for r in rows:
        d = json.loads(r.pop("data") or "{}")
        angle = d.get("angle") or {}
        r.update(hook=angle.get("hook"), offer=angle.get("offer"), connection_note=(d.get("messages") or {}).get("connection_note"),
                 rounds=len(d.get("rounds") or []), first_hand=(d.get("research") or {}).get("first_hand"))
    return rows


def update_messages(pitch_id: int, messages: dict, status: str | None = None) -> dict:
    p = get(pitch_id)
    if not p:
        raise LookupError("Pitch not found")
    data = p["data"]
    data["messages"] = {**(data.get("messages") or {}), **{k: v for k, v in messages.items() if k in MESSAGE_KEYS}}
    with db.session() as s:
        s.execute("UPDATE pitch SET data=?, status=COALESCE(?, status), updated_at=CURRENT_TIMESTAMP WHERE id=?",
                  (json.dumps(data), status, pitch_id))
    return get(pitch_id)


MESSAGE_KEYS = ["connection_note", "message_1"]


# ------------------------------------------------------------------ 1. research


def context(person_id: int, kind: str | None = None, context_id: int | None = None) -> dict:
    """Everything we know that could make a message specific: their initiatives/projects, tech, vendors."""
    with db.session() as s:
        p = dict(s.execute("""SELECT p.*, c.name company, c.industry, c.summary company_summary, c.domain, c.hq_country
                              FROM person p JOIN company c ON c.id=p.company_id WHERE p.id=?""", (person_id,)).fetchone())
        cid = p["company_id"]

        def ev(table, key, iid):
            return [dict(r) for r in s.execute(
                f"""SELECT d.title, d.url, d.source_type, d.published_at, e.quote FROM {table} e JOIN document d ON d.id=e.document_id
                    WHERE e.{key}=? ORDER BY d.published_at DESC LIMIT 4""", (iid,))]

        works = []
        for r in s.execute("""SELECT i.*, ic.role FROM initiative_contact ic JOIN initiative i ON i.id=ic.initiative_id
                              WHERE ic.person_id=? AND COALESCE(i.feedback,'')!='dismissed'""", (person_id,)):
            works.append({"kind": "initiative", "id": r["id"], "name": r["name"], "role": r["role"], "stage": r["stage"],
                          "summary": r["summary"], "tech": json.loads(r["tech"] or "[]"), "fit": r["fit_score"],
                          "fit_reason": r["fit_reason"], "evidence": ev("initiative_evidence", "initiative_id", r["id"])})
        for r in s.execute("""SELECT pr.*, pc.role FROM project_contact pc JOIN project pr ON pr.id=pc.project_id
                              WHERE pc.person_id=? AND COALESCE(pr.feedback,'')!='dismissed'""", (person_id,)):
            works.append({"kind": "project", "id": r["id"], "name": f"{r['name']} ({'for' if r['direction'] == 'client' else 'with'} {r['counterparty']})",
                          "role": r["role"], "stage": r["status"], "summary": r["summary"], "tech": json.loads(r["tech"] or "[]"),
                          "fit": r["fit_score"], "fit_reason": r["fit_reason"], "evidence": ev("project_evidence", "project_id", r["id"])})
        if not works:  # not linked yet: use the company's best-fit work
            for r in s.execute("""SELECT * FROM initiative WHERE company_id=? AND COALESCE(feedback,'')!='dismissed'
                                  ORDER BY fit_score DESC LIMIT 2""", (cid,)):
                works.append({"kind": "initiative", "id": r["id"], "name": r["name"], "role": None, "stage": r["stage"],
                              "summary": r["summary"], "tech": json.loads(r["tech"] or "[]"), "fit": r["fit_score"],
                              "fit_reason": r["fit_reason"], "evidence": ev("initiative_evidence", "initiative_id", r["id"])})
        tech = [r["name"] for r in s.execute("SELECT name FROM tech WHERE company_id=? LIMIT 25", (cid,))]
        vendors = [dict(r) for r in s.execute(
            "SELECT name, relationship, area, is_competitor FROM vendor WHERE company_id=? LIMIT 12", (cid,))]
    works.sort(key=lambda w: (not (kind and w["kind"] == kind and w["id"] == context_id), -(w["fit"] or 0)))
    return {"person": p, "works": works[:4], "tech": tech, "vendors": vendors}


def research(pitch_id: int, person: dict) -> dict:
    if "*" in person["full_name"]:
        _log(pitch_id, "Surname is hidden, so their public statements can't be searched. Using their company's signals only. "
                       "Click Get email first for a person-specific pitch.")
        return {"first_hand": 0, "note": "name hidden"}
    _log(pitch_id, f"Reading what {person['full_name']} has said publicly")
    try:
        b = buyers.build(person["id"])
    except Exception as exc:
        _log(pitch_id, f"Couldn't build their brief ({exc}); using company signals only")
        return {"first_hand": 0, "note": str(exc)}
    fh = b.get("first_hand")
    if fh is None:
        fh = len(b.get("topics") or [])
    _log(pitch_id, f"Found {len(b.get('sources') or [])} sources, {fh} in their own words")
    v = b.get("voice") or {}
    if v.get("samples"):
        _log(pitch_id, f"Their voice: {v.get('summary') or v.get('register')}")
    return {**b, "first_hand": fh}


# ------------------------------------------------------------------ 2. triggers


TRIGGERS = """You are the TRIGGER FINDER. Find what would genuinely hit this specific person: make them stop, feel
seen, or feel a little uneasy. Types: "pain" (a problem they or their company voiced), "commitment" (a public
promise, deadline or go-live they own), "ambition" (what they want to be known for), "event" (something fresh:
launch, hiring spike, new role, funding, outage), "peer_move" (a competitor or peer doing something), "contrarian"
(a widely held belief in their space that is wrong for their situation), "recognition" (a talk or post of theirs
worth engaging with). Only use the material given; say how strong each trigger is for THIS person.
Also do a pre-mortem: the real reasons this person ignores vendor messages."""


def find_triggers(ctx: dict, brief: dict, profile: dict) -> dict:
    prompt = f"""{_seller_block(profile)}

{_buyer_block(ctx, brief)}

Return {{"triggers": [{{"type": one of ["pain","commitment","ambition","event","peer_move","contrarian","recognition"],
  "what": the trigger in one line, "evidence": quote or source line it rests on, "basis": "their_words" or "company_signal",
  "intensity": 1-10 (how hard it hits them), "fresh": true if from the last 90 days}}],
"dismiss_reasons": [3-5 reasons THIS person would ignore a vendor message, e.g. "already has an SI", "gets 40 QA pitches a month"]}}
Strongest first, 3-6 triggers."""
    try:
        out = llm.complete_json(TRIGGERS, prompt, 1800)
    except Exception:
        return {"triggers": [], "dismiss_reasons": []}
    trig = [t for t in (out.get("triggers") or []) if isinstance(t, dict) and t.get("what")]
    return {"triggers": trig, "dismiss_reasons": [str(x) for x in (out.get("dismiss_reasons") or [])][:6]}


HOOK_STYLES = {
    "their_words": "echo something they said and push it one step further",
    "sharp_question": "a precise technical question about their exact situation that they can't answer instantly",
    "risk": "name the specific failure mode their work is about to run into",
    "contrarian": "challenge a common belief that is wrong for their situation",
    "timing": "tie to a deadline, go-live or fresh event of theirs",
    "peer_pattern": "what teams in their position usually get wrong (no invented clients or numbers)",
}

HOOK_WRITER = """You are the HOOK WRITER. Write opening lines for a LinkedIn connection note. Each must name something
specific to this person (their words, system, migration, client, deadline) within the first 12 words, create
curiosity or mild tension, and contain no pitch, no seller name, no compliment and no greeting beyond "Hi <name>,".
Under 160 characters each. One hook per style."""

HOOK_JUDGE = """You are a HOOK JUDGE playing the person described. You see only the LinkedIn notification preview: the
first line of a connection request from a stranger. You get dozens a week and ignore almost all. For each hook, say
honestly whether it would make you stop and open it, and why, in first person."""


def hooks(ctx: dict, brief: dict, angle: dict, trig: dict) -> list[dict]:
    first = ctx["person"]["full_name"].split()[0]
    styles = "\n".join(f"- {k}: {v}" for k, v in HOOK_STYLES.items())
    try:
        out = llm.complete_json(HOOK_WRITER, f"""{_buyer_block(ctx, brief)}

What hits them: {json.dumps(trig.get('triggers', [])[:4])}
Angle: {json.dumps({k: angle.get(k) for k in ('hook', 'evidence', 'technical_insight', 'why_they_care')})}
First name: {first}
Styles:
{styles}

Return {{"hooks": [{{"style": style key, "line": the opening line}}]}}""", 1200)
        cands = [h for h in (out.get("hooks") or []) if isinstance(h, dict) and h.get("line")][:8]
    except Exception:
        return []
    if not cands:
        return []
    try:
        judged = llm.complete_json(HOOK_JUDGE, f"""{_buyer_block(ctx, brief)}

Previews you received:
{chr(10).join(f"{i}. {h['line']}" for i, h in enumerate(cands))}

Return {{"verdicts": [{{"n": number, "stop": 1-10 (how likely you open it), "reaction": first person, one sentence}}]}}""", 1200)
        for v in judged.get("verdicts") or []:
            try:
                i = int(v.get("n"))
                cands[i]["stop"] = float(v.get("stop") or 0)
                cands[i]["reaction"] = v.get("reaction")
            except (TypeError, ValueError, IndexError):
                continue
    except Exception:
        pass
    for h in cands:
        h["stop"] = h.get("stop", 0.0)
        h["generic"] = bool(bland_line(h["line"], ctx))
    cands.sort(key=lambda h: (not h["generic"], h["stop"]), reverse=True)
    return cands


EXPLAINER = """You are the EXPLAINER. Show a salesperson why a pitch should work for this person and what could still
make them refute it. Be concrete and honest; point to exact lines of the messages."""


def explain(ctx: dict, brief: dict, trig: dict, rounds: list[dict], final: dict) -> dict:
    history = [{"round": r["n"], "refutes": (r["simulation"].get("refutes") or []) + r.get("lint", []),
                "score": r["simulation"].get("overall")} for r in rounds]
    try:
        out = llm.complete_json(EXPLAINER, f"""{_buyer_block(ctx, brief)}

What hits them: {json.dumps(trig.get('triggers', []))}
Why they usually ignore vendors: {json.dumps(trig.get('dismiss_reasons', []))}
Push-back across drafting rounds: {json.dumps(history)}
FINAL MESSAGES: {json.dumps(final['messages'])}
Remaining push-back on the final draft: {json.dumps(final['simulation'].get('refutes') or [])}

Return {{"hits": [{{"line": exact phrase from the final messages, "trigger": what it hits for them, "evidence": what it rests on}}],
"beaten": [{{"refute": a push-back or dismiss reason, "how": what the final draft does about it, "line": exact phrase}}],
"still_open": [{{"refute": what could still make them say no, "suggestion": a concrete fix or how to handle it in a reply}}]}}""", 1800)
        return {k: [x for x in (out.get(k) or []) if isinstance(x, dict)] for k in ("hits", "beaten", "still_open")}
    except Exception:
        return {"hits": [], "beaten": [], "still_open": []}


# ------------------------------------------------------------------ 3. strategist


STRATEGIST = """You are the STRATEGIST for a B2B seller's outreach. Find angles where a specific person's own words
or their company's current work meets what the seller can do. A good angle is narrow and technical: it names the
system, migration or launch, and the testing risk an expert would see in it. Rank angles by how likely THIS person
is to care. Never invent facts about the person or the company; use only the material given. The technical insight
may come from expertise, but must be phrased as an observation or question, not as a claim about them."""


def _seller_block(profile: dict) -> str:
    offs = "\n".join(f"- {o['name']} ({o.get('kind', 'service')}): {o.get('what', '')}" for o in profile.get("offerings", []))
    offers = "\n".join(f"- {o['name']}: {o.get('what', '')} Suits: {o.get('for', '')}. Their effort: {o.get('effort_for_them', '')}"
                       for o in profile.get("offers", []))
    proof = "\n".join(f"- {x}" for x in profile.get("proof", []))
    return f"""SELLER: {profile.get('company')}. {profile.get('description', '')}
Offerings:
{offs}
Give-first offers (use ONLY these, by exact name):
{offers or '- none listed: suggest a short, low-effort conversation only'}
Proof points (use ONLY these; never invent clients or numbers):
{proof or '- none'}"""


def _buyer_block(ctx: dict, brief: dict) -> str:
    p = ctx["person"]
    works = "\n".join(
        f"- [{w['kind']}] {w['name']} | their role: {w['role'] or 'not linked'} | stage: {w['stage']} | {w['summary']} | tech: {', '.join(w['tech'][:8])}"
        + "".join(f"\n    source ({e['source_type']}, {e.get('published_at') or 'undated'}): \"{(e.get('quote') or '')[:200]}\"" for e in w["evidence"][:2])
        for w in ctx["works"]) or "- none found"
    topics = "\n".join(f"- {t.get('topic')}: \"{t.get('quote', '')}\" ({t.get('date') or 'undated'})" for t in (brief.get("topics") or [])) or "- nothing first-hand found"
    def pts(key):
        return "; ".join((x.get("text") if isinstance(x, dict) else str(x)) + ("" if isinstance(x, dict) and x.get("source") is not None else " [role-typical]")
                         for x in (brief.get(key) or [])) or "unknown"
    vendors = "; ".join(f"{v['name']} ({v['relationship']}, {v['area']}){' [COMPETITOR]' if v['is_competitor'] else ''}" for v in ctx["vendors"]) or "unknown"
    v = brief.get("voice") or {}
    if v.get("samples"):
        voice = (f"from {v['samples']} of their own texts: {v.get('summary', '')} Register {v.get('register')}, length {v.get('length')}, "
                 f"{v.get('directness')}, makes points with {v.get('evidence')}, energy {v.get('energy')}, emoji/hashtags {v.get('emoji_hashtags')}. "
                 f"Words they use: {', '.join(v.get('vocabulary') or [])}. How they reply: {v.get('how_they_reply') or 'unknown'}. "
                 f"Write to them like this: {'; '.join(v.get('mirror') or [])}. Tone to avoid: {'; '.join(v.get('avoid') or [])}.")
    else:
        voice = "unknown (no first-hand writing found): keep it short, neutral and plain; no hype, no exclamation marks."
    return f"""PERSON: {p['full_name']}, {p.get('title') or 'title unknown'} at {p['company']} ({p.get('industry') or ''}, {p.get('hq_country') or ''})
Company: {p.get('company_summary') or ''}
What they have said themselves:
{topics}
Priorities: {pts('priorities')}
Motivators: {pts('motivators')}
Concerns: {pts('concerns')}
Communication style: {brief.get('communication_style', 'unknown')}. {brief.get('style_note', '')}
Avoid: {pts('avoid')}
Their company's work they are linked to:
{works}
Company tech: {', '.join(ctx['tech'][:20]) or 'unknown'}
Vendors and partners: {vendors}
HOW THEY COMMUNICATE: {voice}"""


def strategize(ctx: dict, brief: dict, profile: dict, trig: dict | None = None) -> dict:
    trig = trig or {}
    prompt = f"""{_seller_block(profile)}

{_buyer_block(ctx, brief)}

What hits them (build angles on the strongest of these): {json.dumps(trig.get('triggers', []))}
Why they'd ignore a vendor (angles must get past these): {json.dumps(trig.get('dismiss_reasons', []))}

Return {{"angles": [{{
  "hook": the specific thing to open on (their statement, their migration/launch, a project with a named client),
  "basis": "their_words" if it rests on something they said, else "company_signal",
  "evidence": the exact quote or source line it rests on,
  "technical_insight": one concrete risk, failure mode or question an expert tester would raise about THIS work
                       (name the system/tech), phrased as an observation,
  "conversation_starter": the thing that makes them WANT to reply: a non-obvious insight, a pattern, a question
                          about their situation they'd enjoy answering, or something useful we could send (no meetings),
  "offering": the seller offering that fits, "offer": exact give-first offer name to bring up only AFTER they reply,
  "proof": one proof point from the list that fits, or null,
  "why_they_care": one sentence tied to their priorities or concerns,
  "strength": 1-10 }}],
"chosen": index of the strongest angle, "skip_reason": null, or a reason this person is a poor target right now}}
Give 2-4 angles, strongest first."""
    out = llm.complete_json(STRATEGIST, prompt, 2500)
    angles = [a for a in (out.get("angles") or []) if isinstance(a, dict) and a.get("hook")]
    if not angles:
        raise RuntimeError("The strategist found no angle")
    try:
        chosen = max(0, min(int(out.get("chosen") or 0), len(angles) - 1))
    except (TypeError, ValueError):
        chosen = 0
    order = [chosen] + [i for i in range(len(angles)) if i != chosen]
    return {"angles": [angles[i] for i in order], "skip_reason": out.get("skip_reason")}


# ------------------------------------------------------------------ 3. writer


WRITER = f"""You are the WRITER of LinkedIn outreach for a B2B seller. Rules:
- The connection note MUST open with the chosen opening hook (lightly edited at most). Every later message
  keeps that thread going; it must not restart with a generic line.
- Open on the hook, about THEM. No greetings beyond "Hi <first name>,". No compliments, no "I came across your profile".
- One technical observation or question that shows expertise in their exact situation. Specific nouns: system names,
  migration steps, device types, failure modes. No generic "quality matters".
- Two messages only. The goal is to START A CONVERSATION, not to sell or book time.
- The connection note asks for nothing and does not pitch.
- Message 1 (after they accept) continues the same thread: one sharp, non-obvious insight about their exact
  situation, then the conversation starter: a question they'd want to answer, or an offer to SEND something useful.
  It ends with one easy question that needs no meeting.
- NEVER ask for time: no calls, meetings, demos, "15/30/45 minutes", calendar links or "this week". No service
  pitch, no list of capabilities. The seller may be named once at most in Message 1, only if it helps credibility.
- Write in THEIR voice, following "HOW THEY COMMUNICATE": match their register, length, directness and the way
  they make a point (numbers vs stories), reuse a word or phrase they actually use where natural, and obey every
  "write to them like this" rule. Two people with different voices must get differently written messages.
- Plain, peer-to-peer.
- Never invent facts, clients, metrics or events. Use only the proof points and offers given.
- Hard limits (characters): connection_note {LIMITS['connection_note']}, message_1 {LIMITS['message_1']}.
- Never use: {', '.join(BANNED)}."""


def write(ctx: dict, brief: dict, profile: dict, angle: dict, previous: dict | None, critique: list[str],
          hook: dict | None = None, trig: dict | None = None) -> dict:
    first = ctx["person"]["full_name"].split()[0]
    revise = ""
    if previous:
        revise = f"""
PREVIOUS DRAFT:
{json.dumps(previous, indent=1)}
WHAT THE BUYER SAID / WHAT TO FIX:
{chr(10).join('- ' + c for c in critique)}
Rewrite to fix every point. Keep what worked."""
    prompt = f"""{_seller_block(profile)}

{_buyer_block(ctx, brief)}

ANGLE TO USE:
{json.dumps(angle, indent=1)}
OPENING HOOK (the connection note starts with this): {hook['line'] if hook else 'write your own, specific to them'}
WHY THEY'D IGNORE A VENDOR (get past these): {json.dumps((trig or {}).get('dismiss_reasons', []))}
First name: {first}
{revise}
Return {{"connection_note": str, "message_1": str}}"""
    out = llm.complete_json(WRITER, prompt, 2000)
    return {k: str(out.get(k) or "").strip() for k in MESSAGE_KEYS}


GENERIC = ["quality engineering", "testing services", "qa services", "solutions", "help companies", "companies like yours",
           "partner with", "our team", "we specialize", "we are a", "i am from", "i'm from", "industry leader"]


def _specific_terms(ctx: dict) -> set[str]:
    """Words that only make sense for this person: their tech, initiative/project names, counterparties, company."""
    words = set()
    for t in ctx["tech"] + [x for w in ctx["works"] for x in w["tech"]]:
        words.add(t.lower())
    for w in ctx["works"]:
        words |= {x.lower() for x in re.findall(r"[A-Za-z][A-Za-z0-9+.-]{3,}", w["name"])}
    for v in ctx["vendors"]:
        words.add(v["name"].lower())
    words.add(ctx["person"]["company"].lower().split()[0])
    return {w for w in words if len(w) >= 3} - {"with", "from", "platform", "programme", "program", "project", "initiative", "rollout"}


def bland_line(line: str, ctx: dict) -> str | None:
    head = line.lower()[:170]
    if not any(t in head for t in _specific_terms(ctx)):
        return "The opening names nothing specific to them. Put their system, project, client or own words in the first line."
    return None


def lint(msgs: dict, ctx: dict | None = None, seller: str = "") -> list[str]:
    """Hard checks the simulator might miss: length limits, banned phrases, placeholders, bland openings."""
    issues = []
    note = msgs.get("connection_note", "")
    if ctx and note:
        b = bland_line(note, ctx)
        if b:
            issues.append(b)
        body = re.sub(r"^hi [^,]+,\s*", "", note.strip(), flags=re.I).lower()
        if body.startswith(("i ", "i'm", "we ", "we're", "my name", "our ")):
            issues.append("The connection note starts with you. Start with them.")
        if seller and seller.lower() in note.lower():
            issues.append(f"Don't name {seller} in the connection note; earn the click first.")
        for g in GENERIC:
            if g in note.lower():
                issues.append(f'"{g}" in the connection note sounds like every vendor.')
    for k, lim in LIMITS.items():
        if len(msgs.get(k, "")) > lim:
            issues.append(f"{k} is {len(msgs[k])} characters; the limit is {lim}. Cut it.")
        if not msgs.get(k):
            issues.append(f"{k} is empty.")
    text = " ".join(msgs.values()).lower()
    for b in BANNED:
        if b in text:
            issues.append(f'Remove the phrase "{b}".')
    for k in MESSAGE_KEYS:
        m = TIME_ASK.search(msgs.get(k, ""))
        if m:
            issues.append(f'{k} asks for time ("{m.group(0)}"). Do not ask for a call or minutes; end with a question they want to answer.')
    if re.search(r"\[[^\]]+\]|\{[^}]+\}|<[^>]+>", " ".join(msgs.values())):
        issues.append("Remove placeholders like [name] or {company}; write the real text.")
    return issues


# ------------------------------------------------------------------ 4. buyer simulator


SIMULATOR = """You are a BUYER SIMULATOR. You play the person described: busy, senior, and receiving 30+ vendor
messages a week on LinkedIn. You ignore anything generic, flattering, vague or that could have been sent to anyone.
You respond only when a message shows the sender understands YOUR situation and offers something worth your time.
React honestly as that person, in first person, using what is known about their priorities, concerns and style.
Then step out of character and score the draft strictly. Most outreach scores 3-5."""


def simulate(ctx: dict, brief: dict, msgs: dict) -> dict:
    prompt = f"""{_buyer_block(ctx, brief)}

THE TWO MESSAGES YOU RECEIVED (a connection request, then a message after you accept):
{json.dumps(msgs, indent=1)}

Return {{"connection": {{"accept": true/false, "reaction": "first person, one or two sentences"}},
"message_1": {{"reply": true/false (would you reply and start a conversation), "reaction": "first person"}},
"refutes": [things you'd push back on or doubt, in your own voice],
"scores": {{"hook": 1-10 (would the first line make you stop scrolling), "tone": 1-10 (does it sound like someone you'd talk to,
            given how YOU write and reply), "relevance": 1-10, "specificity": 1-10,
            "credibility": 1-10, "ease_of_reply": 1-10}},
"overall": 1-10,
"fixes": [concrete edits that would change your answer, e.g. "name the Pega version", "drop the second question"]}}"""
    out = llm.complete_json(SIMULATOR, prompt, 1500)
    try:
        out["overall"] = float(out.get("overall") or 0)
    except (TypeError, ValueError):
        out["overall"] = 0.0
    return out


def passed(sim: dict, issues: list[str]) -> bool:
    hook = (sim.get("scores") or {}).get("hook")
    try:
        if hook is not None and float(hook) < 7:
            return False
    except (TypeError, ValueError):
        pass
    return (not issues and sim["overall"] >= PASS_SCORE and (sim.get("connection") or {}).get("accept") is True
            and (sim.get("message_1") or {}).get("reply") is True)


# ------------------------------------------------------------------ 6. objections


OBJECTIONS = """You prepare a seller for OBJECTIONS. Given the person, the sequence and the buyer simulator's
push-back, list the replies this person is most likely to send and two good answers to each. Answers are short,
honest, never pushy, and use only the seller's real proof points and offers."""


def objections(ctx: dict, brief: dict, profile: dict, msgs: dict, sim: dict) -> list[dict]:
    prompt = f"""{_seller_block(profile)}

{_buyer_block(ctx, brief)}

FINAL MESSAGES: {json.dumps(msgs)}
SIMULATED PUSH-BACK: {json.dumps(sim.get('refutes') or [])}

Return {{"objections": [{{"objection": what they'd say, in their voice, "likelihood": "high"|"medium"|"low",
"responses": [{{"label": 2-4 word approach, "reply": the message to send}}, {{...}}]}}]}} with 3-5 objections,
including "we already have in-house QA / a vendor" and "send me a deck" if they apply."""
    out = llm.complete_json(OBJECTIONS, prompt, 2000)
    return [o for o in (out.get("objections") or []) if isinstance(o, dict) and o.get("objection")]


# ------------------------------------------------------------------ orchestration


def run(pitch_id: int) -> None:
    with db.session() as s:
        r = s.execute("SELECT person_id FROM pitch WHERE id=?", (pitch_id,)).fetchone()
    with tenancy.use((tenancy.of_person(r["person_id"]) if r else None) or 1):
        _run(pitch_id)


def _run(pitch_id: int) -> None:
    with db.session() as s:
        row = dict(s.execute("SELECT * FROM pitch WHERE id=?", (pitch_id,)).fetchone())
        s.execute("UPDATE pitch SET status='running', updated_at=CURRENT_TIMESTAMP WHERE id=?", (pitch_id,))
    try:
        if not llm.available():
            raise RuntimeError("Pitches need OPENAI_API_KEY or ANTHROPIC_API_KEY")
        profile = profiles.load()
        ctx = context(row["person_id"], row.get("context_kind"), row.get("context_id"))
        brief = research(pitch_id, ctx["person"])
        _log(pitch_id, f"Context: {len(ctx['works'])} initiative(s)/project(s), {len(ctx['tech'])} tech, {len(ctx['vendors'])} vendors")

        _log(pitch_id, "Finding what would actually hit them, and why they'd ignore a vendor")
        trig = find_triggers(ctx, brief, profile)
        if trig["triggers"]:
            _log(pitch_id, f"Strongest trigger ({trig['triggers'][0].get('type')}): {trig['triggers'][0]['what']}")

        _log(pitch_id, "Strategist: finding angles where their world meets what you sell")
        strat = strategize(ctx, brief, profile, trig)
        angles = strat["angles"]
        _log(pitch_id, f"{len(angles)} angle(s); starting with: {angles[0]['hook']}")

        hook_sets: dict[int, list] = {}

        def pick_hook(i: int):
            if i not in hook_sets:
                _log(pitch_id, f"Writing {len(HOOK_STYLES)} opening hooks and testing which one makes them stop scrolling")
                hook_sets[i] = hooks(ctx, brief, angles[i], trig)
                if hook_sets[i]:
                    h = hook_sets[i][0]
                    _log(pitch_id, f"Winning hook ({h['style']}, {h['stop']:g}/10): {h['line']}")
            return hook_sets[i][0] if hook_sets[i] else None

        rounds, best = [], None
        a, msgs, critique, tries_on_angle = 0, None, [], 0
        for n in range(1, MAX_ROUNDS + 1):
            angle = angles[a]
            hook = pick_hook(a)
            _log(pitch_id, f"Round {n}: writing" + (" a revision" if msgs else ""))
            msgs = write(ctx, brief, profile, angle, msgs, critique, hook, trig)
            issues = lint(msgs, ctx, profile.get("company", ""))
            sim = simulate(ctx, brief, msgs)
            rounds.append({"n": n, "angle": a, "hook": hook["line"] if hook else None, "messages": msgs, "simulation": sim, "lint": issues})
            verdict = ("accepts" if (sim.get("connection") or {}).get("accept") else "ignores") + " the invite, " + \
                      ("would reply" if (sim.get("message_1") or {}).get("reply") else "would not reply")
            _log(pitch_id, f"Round {n}: buyer {verdict}; score {sim['overall']:g}/10" + (f"; {len(issues)} rule issue(s)" if issues else ""))
            if best is None or (sim["overall"] - len(issues)) > (best["simulation"]["overall"] - len(best["lint"])):
                best = rounds[-1]
            if passed(sim, issues):
                break
            tries_on_angle += 1
            critique = issues + [str(x) for x in (sim.get("refutes") or [])] + [str(x) for x in (sim.get("fixes") or [])]
            if tries_on_angle >= 2 and sim["overall"] < 6 and a + 1 < len(angles):
                a, msgs, critique, tries_on_angle = a + 1, None, [], 0
                _log(pitch_id, f"Angle isn't landing; switching to: {angles[a]['hook']}")

        _log(pitch_id, "Explaining why it should land and what could still get it refuted")
        why = explain(ctx, brief, trig, rounds, best)
        _log(pitch_id, "Preparing answers to likely objections")
        try:
            objs = objections(ctx, brief, profile, best["messages"], best["simulation"])
        except Exception as exc:
            objs = []
            _log(pitch_id, f"Objections step failed: {exc}")

        warnings = []
        if not ctx["person"].get("linkedin_url"):
            warnings.append("No LinkedIn URL yet. Dripify needs it: click Get email to fetch it.")
        if "*" in ctx["person"]["full_name"]:
            warnings.append("Surname hidden: the pitch uses company signals only. Get email, then regenerate for a person-specific pitch.")
        if not brief.get("first_hand"):
            warnings.append("Nothing first-hand from this person was found, so the hook rests on their company's work and the tone is a "
                            "neutral default. Paste a few things they wrote or said (LinkedIn posts, comments, talk quotes) in the box below, then regenerate.")
        if best is not rounds[-1] or not passed(best["simulation"], best["lint"]):
            warnings.append(f"Best draft scored {best['simulation']['overall']:g}/10 against a pass mark of {PASS_SCORE:g}. Review before sending.")
        data = {"angle": angles[best["angle"]], "angles": angles, "triggers": trig["triggers"],
                "dismiss_reasons": trig["dismiss_reasons"], "hooks": hook_sets.get(best["angle"], []), "why": why, "messages": best["messages"], "simulation": best["simulation"],
                "rounds": rounds, "objections": objs, "warnings": warnings, "skip_reason": strat.get("skip_reason"),
                "research": {"first_hand": brief.get("first_hand", 0), "topics": brief.get("topics") or [], "voice": brief.get("voice") or {},
                             "sources": brief.get("sources") or [], "style": brief.get("communication_style")},
                "context": [{"kind": w["kind"], "id": w["id"], "name": w["name"]} for w in ctx["works"]]}
        with db.session() as s:
            s.execute("UPDATE pitch SET status='ready', score=?, data=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (best["simulation"]["overall"], json.dumps(data), pitch_id))
        _log(pitch_id, f"Done: {len(rounds)} round(s), final score {best['simulation']['overall']:g}/10")
    except Exception as exc:
        with db.session() as s:
            s.execute("UPDATE pitch SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (config.redact(str(exc)), pitch_id))
        _log(pitch_id, f"Failed: {exc}")


def top_contacts(company_id: int, limit: int = 5, min_fit: float = 0.5) -> list[int]:
    """The people most worth pitching at a company: strong contact on a strong-fit initiative or project."""
    with db.session() as s:
        rows = s.execute(
            """SELECT person_id, MAX(score) s FROM (
                 SELECT ic.person_id, ic.score * COALESCE(i.fit_score, 0) score FROM initiative_contact ic
                   JOIN initiative i ON i.id=ic.initiative_id
                   WHERE i.company_id=? AND COALESCE(i.fit_score,0) >= ? AND COALESCE(ic.feedback,'')!='rejected'
                     AND COALESCE(i.feedback,'')!='dismissed'
                 UNION ALL
                 SELECT pc.person_id, pc.score * COALESCE(pr.fit_score, 0) FROM project_contact pc
                   JOIN project pr ON pr.id=pc.project_id
                   WHERE pr.company_id=? AND COALESCE(pr.fit_score,0) >= ? AND COALESCE(pc.feedback,'')!='rejected'
                     AND COALESCE(pr.feedback,'')!='dismissed')
               GROUP BY person_id ORDER BY s DESC LIMIT ?""", (company_id, min_fit, company_id, min_fit, limit)).fetchall()
    return [r["person_id"] for r in rows]


def run_queue(pitch_ids: list[int]) -> None:
    for pid in pitch_ids:
        run(pid)


# ------------------------------------------------------------------ export


def dripify_csv(pitch_ids: list[int]) -> str:
    """One row per lead. In Dripify, map each message column to a Custom Lead Field and use it as a variable."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["LinkedIn URL", "First name", "Last name", "Company", "Title", "Email", "Connection note", "Message 1",
                "Hook", "Offer after reply", "Score"])
    for pid in pitch_ids:
        p = get(pid)
        if not p or p["status"] not in ("ready", "approved", "exported"):
            continue
        m = p["data"].get("messages") or {}
        parts = p["full_name"].split()
        w.writerow([p.get("linkedin_url") or "", parts[0], " ".join(parts[1:]), p["company"], p.get("title") or "", p.get("email") or "",
                    m.get("connection_note", ""), m.get("message_1", ""), (p["data"].get("angle") or {}).get("hook", ""),
                    (p["data"].get("angle") or {}).get("offer", ""), p.get("score") or ""])
    with db.session() as s:
        s.executemany("UPDATE pitch SET status='exported' WHERE id=? AND status IN ('ready','approved')", [(i,) for i in pitch_ids])
    return buf.getvalue()
