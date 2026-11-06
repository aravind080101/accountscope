"""What an action will spend, shown to the user before they confirm it.

Counts come from the code paths themselves: the brief's web searches (buyers.search_plan), the pitch
agent's AI calls (pitch.py: triggers, strategy, hook writer, hook judge, explainer, objections, then a
write + simulate pair per round, up to MAX_ROUNDS), and Apollo's per-contact reveal.
"""
from . import buyers, config, db, pitch

TAVILY_CREDITS_PER_SEARCH = 2   # tavily.raw_search uses search_depth="advanced"
PITCH_FIXED_AI_CALLS = 6        # triggers, strategize, hook writer, hook judge, explain, objections
BRIEF_AI_CALLS = 1


def _person(pid: int) -> dict:
    with db.session() as s:
        row = s.execute("""SELECT p.id, p.full_name, p.title, p.email, c.name company, c.domain
                           FROM person p JOIN company c ON c.id=p.company_id WHERE p.id=?""", (pid,)).fetchone()
    if not row:
        raise LookupError("Person not found")
    return dict(row)


def _brief_part(p: dict, force: bool = False) -> tuple[int, int]:
    """(web searches, AI calls) to build this person's brief; (0, 0) when the saved one is reused."""
    if not buyers.needs_rebuild(p["id"], force):
        return 0, 0
    return len(buyers.search_plan(p["full_name"], p["company"], p.get("title") or "", p.get("domain"))), BRIEF_AI_CALLS


def _summary(people: list[dict], searches: int, ai_min: int, ai_max: int, apollo: int, reused: int, notes: list[str]) -> dict:
    lines = []
    if apollo:
        lines.append({"service": "Apollo", "amount": f"{apollo} credit{'s' if apollo != 1 else ''}",
                      "detail": "to reveal the email and full name"})
    if searches:
        lines.append({"service": "Tavily", "amount": f"up to {searches * TAVILY_CREDITS_PER_SEARCH} credits",
                      "detail": f"{searches} web searches for what they've said publicly (fewer if recently cached)"})
    if ai_max:
        provider = {"openai": "OpenAI", "anthropic": "Anthropic"}.get(config.llm_provider() or "", "AI provider")
        calls = f"{ai_min}–{ai_max}" if ai_min != ai_max else str(ai_max)
        lines.append({"service": provider, "amount": f"{calls} AI calls",
                      "detail": "billed by tokens on your API key; more rounds only if a draft fails the buyer test"})
    if reused:
        notes.append(f"Reuses the buyer brief already saved for {reused} {'person' if reused == 1 else 'people'}: no search credits for them.")
    return {"people": len(people), "lines": lines, "notes": notes, "free": not lines}


def enrich(pid: int) -> dict:
    p = _person(pid)
    if p.get("email"):
        return _summary([p], 0, 0, 0, 0, 0, ["Already revealed: nothing will be charged."])
    return _summary([p], 0, 0, 0, 1, 0, ["Apollo may not charge if it has no email for this person."])


def brief(pid: int, force: bool = False) -> dict:
    p = _person(pid)
    searches, ai = _brief_part(p, force)
    return _summary([p], searches, ai, ai, 0, 0 if searches else 1, [])


def pitches(pids: list[int]) -> dict:
    people = [_person(pid) for pid in pids]
    searches = ai_min = ai_max = reused = 0
    notes = []
    masked = [p["full_name"] for p in people if "*" in p["full_name"]]
    for p in people:
        if "*" in p["full_name"]:
            continue  # fails straight away, nothing spent
        s, a = _brief_part(p)
        searches += s
        reused += 0 if s else 1
        ai_min += a + PITCH_FIXED_AI_CALLS + 2          # one write + simulate round
        ai_max += a + PITCH_FIXED_AI_CALLS + 2 * pitch.MAX_ROUNDS
    if masked:
        notes.append(f"{', '.join(masked)}: surname hidden. Click Get email first, or this pitch will stop without spending anything.")
    if not people:
        notes.append("No contacts strong enough to pitch yet.")
    return _summary(people, searches, ai_min, ai_max, 0, reused, notes)
