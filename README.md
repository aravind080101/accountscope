# AccountScope

**Which initiatives is a company running right now, and who owns each one?**

AccountScope is a Draup-style account-intelligence tool for IT services and consulting
sellers. You type in a target company. It reads public signals (job posts, news, filings,
engineering blogs), works out the initiatives behind them, and ranks the people most likely
to **own, sponsor, influence or work on** each initiative. Every claim links to its evidence.

The seller profile (what *you* sell) decides which initiatives count as a fit and who your
buyer persona is. It ships with **Moolya + Bugasura** as the starting profile, written from their
public sites. Replace or sharpen it in **Selling as → What you sell**.

## What you sell: decks, web research, AI fit

- **Upload decks**: PDF, PowerPoint (.pptx), Word or text. Sales decks, case studies, capability
  one-pagers. Export old .ppt or Keynote files to PDF first.
- **Research on the web**: list `Company, domain` lines (default: Moolya and Bugasura). Tavily reads
  their own sites plus public pages about them (about 5 searches per company).
- **Build profile from sources**: the AI reads everything and writes the offerings in your own
  terms (services and products separately), the problems that create demand for each, proof
  points and buyer titles. There are no fixed categories or keyword lists. Edit any of it by hand.
- **Fit** is judged by the AI: it reads every initiative of an account against those offerings
  in one call and returns a score, the offering that fits and a one-line reason. An office move
  scores low even if it mentions "app"; a GenAI launch scores high for AI testing even without
  the word "testing".
- **Re-score all accounts** re-judges fit on everything already researched, with no new web searches.
- The research step also asks the AI who would own each specific initiative, and those titles are
  added to the people search alongside the usual ones.

## Logins and client workspaces

The app is multi-company. Each **workspace** is one client company, with its own accounts, research,
"What you sell" profile, decks, pitches, feedback learning and team. Nothing crosses between workspaces:
every API call is checked against the signed-in user's workspace, and ids from another workspace
answer "not found".

- **Platform owner** (you): creates workspaces and their first admin, and can open any workspace.
- **Workspace admin**: adds teammates, resets their passwords, deactivates people.
- **Member**: uses the app.

New users get a one-time temporary password and must set their own at first sign-in (10+ characters,
mixed case, a number). Passwords are stored as salted scrypt hashes. Sessions are HttpOnly cookies
(Secure in the cloud), last 14 days, and end everywhere when a password changes or a user is deactivated.
Repeated wrong passwords are slowed down.

On your Mac, the first visit shows **Create the owner account**. Everything you researched before
this version moves into that first workspace automatically. Set `REQUIRE_LOGIN=off` in `.env` to use
it alone without signing in.

## Deploy to Cloudflare

See **DEPLOY.md**. In short: a Worker serves the app from a Cloudflare Container, all data lives in
Cloudflare D1, and a Cron Trigger runs the watchlist. You need the Workers Paid plan, Docker Desktop and
Node.js; then `npm install`, `npx wrangler login`, add the secrets, `npx wrangler deploy`.

## Discover: find companies without typing names

- **Signal radar**: pick a signal (hiring testers, launching an app, platform migration, rolling
  out GenAI, new tech leader, raised funding, opening a tech centre, outages) or describe your
  own, then set a region and time window. The app searches recent news and job posts, and the
  LLM lists the companies showing that signal, each with a one-line reason and its source.
- **Browse by filters**: industry keywords, country and employee count, via Apollo company
  search (may use Apollo credits depending on your plan).
- Tick the companies you want and click **Research**. They are researched one after another
  and appear in your accounts list.

## Outreach: the pitch agent

Click the wand on any contact (or **Write pitches** on an account for its top 5 contacts). A chain
of agents runs, and you can watch each step:

1. **Researcher** searches many kinds of source, each tagged by how much it shows their real voice:
   talks and panels, podcasts and videos, interviews in trade media (ET CIO, CIO.com, AIM, YourStory,
   Forbes India, Healthcare IT News, Finextra and more), their own writing (Medium, Substack, public
   LinkedIn posts and articles, X, Quora, GitHub, slides), their company's site, bios, and news quotes.
   Unscripted sources count most for voice; press quotes count least. About 7-9 searches per person,
   cached for 30 days. It searches under every name their employer
   goes by (from the title, e.g. "CIO, Carelon Specialty Care" also searches "Carelon"). It keeps a page
   only if it has their full name and one of those company names. Every point is tagged **Their words**
   or **Role-typical**. It adds their company's initiatives, projects, tech and vendors.
   **How they communicate**: from text they wrote or said (register, length, directness, numbers vs
   stories, words they use, emoji, how they reply), with rules for writing to them. Search engines
   can't read most LinkedIn posts and comments, so the brief has a **Paste their posts** box. Two to five
   pasted posts or comments give a much better read; the brief rebuilds when you add one.
2. **Trigger finder** works out what would hit this person: a pain they voiced, a public commitment
   or go-live they own, an ambition, a fresh event, a peer's move, a contrarian truth, or a talk of
   theirs. It also runs a pre-mortem: why they ignore vendors (an SI owns testing, too many QA pitches).
3. **Strategist** finds 2-4 angles where their words or their company's work meet what you sell.
   Each angle names the system or migration and a technical insight an expert tester would raise,
   then picks one give-first offer from your offer library (**What you sell → offers**).
4. **Hooks**: six opening lines in different styles (their words, sharp question, risk, contrarian,
   timing, peer pattern). The simulated person sees only the LinkedIn preview and scores how likely
   they'd open each one. Hooks that name nothing specific to them are disqualified. The winner opens
   the connection note.
5. **Writer** drafts two messages: the connection note (280 characters; set `CONNECTION_NOTE_MAX=200`
   on a free LinkedIn account) opening on the winning hook, and Message 1, which continues the thread
   with one sharp insight and a question they'd want to answer. Neither asks for time: calls,
   meetings, demos and "N minutes" are rejected. The offer is held back until they reply.
6. **Buyer simulator** plays the person: busy, skeptical, flooded with vendor messages, and judges
   whether the tone sounds like someone they'd talk to, given how they write. It says
   whether it would accept and reply, what it would push back on, and scores the draft.
7. **Rewrite loop**: the writer revises from that critique (plus hard checks on length, banned
   phrases, placeholders and bland openings: no specific term in the first line, starting with "I/We",
   naming the seller, vendor-speak) until the simulated buyer would accept and reply, with a score of 7.5
   or more and a hook score of 7 or more. If an angle keeps failing, it switches angles. Every round is kept so you can see what changed.
8. **Why this works**: which line hits which trigger, which push-back each draft beat, and what
   could still get it refuted (with a fix).
9. **Objections**: the replies they're likely to send ("our SI owns testing", "send a deck"), with
   two ready answers each.

Nothing is sent automatically. On **Outreach**: review, edit and approve, then **Export as CSV**.
In Dripify, upload the CSV to a campaign, map *Connection note* and *Message 1* to Custom Lead
Fields, and put those variables in the invite and the first message step. Each lead gets their
own messages. Dripify needs the LinkedIn URL; **Get email** fetches it.

Cost per pitch: about 3 Tavily searches (cached for 30 days) and 9-13 AI calls.

## Projects (client and partner engagements)

A **project** is a named piece of work between the company and one specific other company, which
is different from an initiative (the company's own internal programme):

- **For clients**: the company delivers the work ("Infosys modernises Aviva's claims platform").
- **With partners**: a named partner delivers it for the company ("Temenos implements Zen's core banking").

They come from deal-win and "selected by" news, case studies (including the company's own site)
and press releases. Each project shows the counterparty, status (announced, won, in progress, live,
completed), value, start date and duration, scope, tech, the people at the company who run it
(named in sources first, then Apollo by delivery titles) and the people named on the client side.
**Research {client} too** adds the counterparty as an account, since it is often a lead itself.
Fit is judged by the AI against what you sell, the same way as for initiatives.

Projects are never removed by **Research again**: new findings are merged in, and old ones stay.
Only **Not relevant** hides one.

## What counts as an initiative

An initiative is the underlying work: a migration, launch, platform build, rollout or new centre. Job
posts are evidence of an initiative, not initiatives themselves. After reading the sources, a second AI
pass groups all the clues into distinct initiatives. Several related job posts land under one
initiative, named after the work ("Snowflake data platform build-out"), not the hiring. Each initiative
is labelled **Publicly described** (news, case study, filing, blog or public post) or **Inferred
from hiring only** (job posts only; confidence capped at 50%, so verify before outreach).

## What it reads

Full pages, not search snippets: vendor case studies, press releases, employees' public posts,
news, job posts on public job boards (Naukri, LinkedIn Jobs,
Indeed, foundit, Instahyre, Greenhouse, Lever, Workday and other applicant-tracking sites), the
company's own careers pages and newsroom, annual reports and earnings coverage, engineering
blogs, vendor announcements and tech-stack mentions. Pages are stored, so re-research only adds
what's new. For guaranteed job-board coverage at scale, plug a licensed job-data provider into
`backend/providers/` alongside Tavily.

## Org chart

Each account has a likely org chart. People come from the sources and, with Apollo and the
company's website, its leadership team. Reporting lines are either **confirmed** (a source said
"reports to the Director of QA") or **inferred** (same function, next level up by seniority,
else the function's C-level, else the CEO). Pick an initiative to highlight its owner, sponsor
and influencers in the tree.

## Watchlists and alerts

Click **Watch weekly** on an account. While the app is running, watched accounts are
re-researched every `WATCH_INTERVAL_DAYS` (default 7). Each run is compared with the previous
one, and these show up under **Alerts**: new initiatives, initiatives moving stage, new leaders in
the news, hiring surges (5+ job posts in 30 days, up 3+ from last time), and new vendors.

If the app isn't always running, schedule this instead (example: daily at 7am):

```
0 7 * * *  cd /path/to/accountscope && .venv/bin/python -m backend.watch
```

## Buyer briefs (buyer psychology)

Click **Buyer brief** on any contact. The app searches what that person has said publicly
(interviews, talks, podcasts, articles, public posts, quotes in news), keeps only sources that
mention them, and the AI writes a brief: what they focus on, their communication style
(data-driven, visionary, pragmatic, technical or relationship-led), what drives and worries them,
how to open, what to avoid, and how your offerings connect, with their own words quoted and
linked. Professional statements only; nothing personal is inferred. A brief costs about three
searches and one AI call, and is cached for 30 days (**Refresh** rebuilds it). Hidden surnames
must be revealed with **Get email** first.

## Footprint (locations and R&D)

The **Footprint** tab lists the company's own sites from the sources: headquarters, offices, R&D
and engineering centres, global capability centres, delivery centres and plants, with what
happens there and headcount when stated. **Where they're hiring** counts open roles per city
from the job posts, which often shows where an initiative's team sits.

## Deal history

The **Vendors & deals** tab shows who the company has bought from, newest first: vendor, what for,
new / renewal / expansion / ended, value and duration when stated, with the quote and source.
Drawn from deal news, vendor press releases and case studies. Competitors in your seller profile
are flagged.

## Tech stack and vendors

The **Tech & vendors** tab lists who the company buys from (selected, partner, current vendor,
being replaced, evaluating), each with the quote and source, and the technologies seen in its
job posts, blogs and news. **On their website** lists what the company's homepage runs
(framework, CMS, e-commerce, analytics, CDN, payments, chat), detected for free by matching its
HTML, scripts and headers against open-source Wappalyzer fingerprints (`wappalyzer-python3`,
GPLv3). No key or credits needed; results are cached for 30 days. BuiltWith is optional and paid. Put your
competitors in the seller profile (`"competitors": [...]`) to flag accounts already using one.

## Feedback loop and caching

- **Right person / Wrong** on each contact. Wrong people are never suggested again for that
  company and kind of initiative; confirmed people are pinned to the top.
- Every verdict also teaches the scoring which **job titles** really own each kind of initiative,
  and that learning applies to every company you research afterwards.
- **Not relevant** on an initiative hides it and skips it in future research of that company.
- **Research again keeps your work.** Initiatives where you fetched an email or marked a contact
  or the initiative are kept. If the new research finds the same work, it is updated in place
  (stage, summary, evidence, fit) and keeps its contacts; if not, it stays on the list as it was.
  Revealed names from Get email are matched by Apollo id, so masked duplicates don't reappear.
  Contacts you marked **Wrong** are removed.
- Pages, Apollo people searches and BuiltWith lookups are cached (`SOURCE_CACHE_HOURS`,
  `PEOPLE_CACHE_DAYS`), so repeat research doesn't re-spend credits. **Research again** always
  searches fresh. Over time the database becomes your own pre-researched account base.

## How it works

```
company name
   │
   ▼
1. Collect     Tavily web search: job posts, news, filings, engineering blogs (last 12 months)
2. Extract     the LLM (Claude or GPT) reads the documents → candidate initiatives with category, stage,
               tech, evidence quotes and any people named in the text
3. Cluster     merges candidates that describe the same initiative
4. Find people people named in the evidence  +  Apollo people search by the titles that
               usually own / sponsor / work on that category  +  your buyer persona
5. Score       role (Owner / Sponsor / Influencer / Practitioner) and a 0–100 score from:
               named in evidence (45) · title fit (30) · role weight · recency · buyer persona
6. Fit         the AI judges each initiative against your offerings (score, offering, reason)
7. Activate    copy a personalised opener, reveal email via Apollo (spends a credit), export CSV
```

The key rule is **no evidence, no claim**. Initiatives come only from documents. A person is
labelled "named in sources" only when a document names them. Everyone else is marked as a
title-based guess.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # add keys for live mode (optional)
uvicorn backend.app:app --reload
```

Open http://localhost:8000.

- **Required:** `TAVILY_API_KEY` plus one LLM key: `ANTHROPIC_API_KEY` (Claude) **or**
  `OPENAI_API_KEY` (GPT, default model `gpt-5.6-sol`, change with `OPENAI_MODEL`). With these you
  can research any real company in any country. If both LLM keys are set, Claude is used unless
  `LLM_PROVIDER=openai`.
- **Recommended:** `APOLLO_API_KEY`. Without it, contacts are limited to people named in the
  sources. With it, the app also finds people by job title and can reveal emails.
- Research one company at a time, or paste a list (one per line, `Company, domain`) into
  **Research a list**. Companies are researched one after another to respect API rate limits.
- Adding the website domain improves the people search a lot.

To change the UI: `cd frontend-react && npm install && npm run build` (or `npm run dev` for live reload on port 5173, with `/api` proxied to port 8000).

Tests: `pytest -q` (runs offline; external APIs are replaced by stand-in responses in the tests).

## Project layout

| Path | What it is |
| --- | --- |
| `backend/app.py` | FastAPI routes + serves the frontend |
| `backend/pipeline.py` | collect → extract → cluster → people → score → save |
| `backend/taxonomy.py` | initiative categories and the titles that usually own/sponsor/run each |
| `backend/buyers.py` | buyer briefs from public professional statements |
| `backend/orgchart.py` | likely org chart: confirmed + inferred reporting lines |
| `backend/alerts.py` | snapshots, diffs, alerts, weekly watchlist scheduler |
| `backend/watch.py` | cron entry point for watched accounts |
| `backend/feedback.py` | contact/initiative verdicts and title learning across companies |
| `backend/cache.py` | SQLite cache for API results |
| `backend/providers/webtech.py` | free website tech detection (open-source fingerprints) |
| `backend/providers/builtwith.py` | optional paid website tech stack |
| `backend/discover.py` | signal radar (Tavily + LLM) and company browsing (Apollo) |
| `backend/auth.py` | sign-in, sessions, roles, team and workspace admin |
| `backend/tenancy.py`, `backend/guard.py` | current workspace, and ownership checks on every id |
| `cloudflare/worker.ts`, `wrangler.jsonc`, `Dockerfile` | Cloudflare deployment (Worker, Container, D1, Cron) |
| `scripts/export_for_d1.py` | copy local data into the cloud database |
| `backend/pitch.py` | pitch agent: strategist, writer, buyer simulator loop, objections, Dripify CSV |
| `backend/projects.py` | client/partner projects: merge, save, contacts |
| `backend/profiles.py` | seller profile (Moolya + Bugasura seed), decks and web material, AI fit |
| `backend/providers/tavily.py` | web search queries per signal type |
| `backend/providers/apollo.py` | people search (free) and enrichment (paid credit) |
| `backend/llm.py` | LLM wrapper (Anthropic or OpenAI) returning JSON |
| `backend/db.py` | SQLite schema |
| `frontend-react/` | the UI: React + Tailwind + shadcn-style components. `dist/` is prebuilt and served by FastAPI, so Node is not needed to run the app |
| `frontend/` | older plain-JS UI, used only if `frontend-react/dist` is missing |

## API

| Method | Path | Does |
| --- | --- | --- |
| POST | `/api/accounts` `{name, domain?}` | create an account and start research |
| POST | `/api/accounts/bulk` `{companies: [{name, domain?}]}` | queue up to 500 companies |
| GET | `/api/accounts` | list accounts |
| GET | `/api/accounts/{id}` | initiatives, contacts, evidence, latest run |
| POST | `/api/accounts/{id}/refresh` | re-run research |
| GET | `/api/accounts/{id}/export.csv` | contacts + openers + evidence URLs |
| POST | `/api/contacts/{id}/enrich` | reveal email/phone via Apollo |
| POST | `/api/discover/signals` `{preset?, query?, region?, days}` | companies showing a signal |
| POST | `/api/discover/companies` `{keywords?, location?, size?, page}` | browse companies (Apollo) |
| GET | `/api/accounts/{id}/org` | org chart nodes and reporting lines |
| GET | `/api/accounts/{id}/tech` | deal history (vendors) and tech stack |
| GET | `/api/accounts/{id}/footprint` | sites and hiring by city |
| GET/POST | `/api/people/{id}/brief?force=` | read or build a buyer brief |
| POST | `/api/accounts/{id}/watch` `{watch}` | watch weekly on/off |
| POST | `/api/accounts/{id}/refresh?force=true` | research again (force = search fresh) |
| GET | `/api/alerts?company_id=&unread=` | changes found at watched accounts |
| POST | `/api/alerts/read` `{ids? , company_id?}` | mark alerts read |
| POST | `/api/contacts/{id}/feedback` `{verdict}` | confirmed, rejected or clear |
| POST | `/api/initiatives/{id}/feedback` `{verdict}` | confirmed, dismissed or clear |
| GET/PUT | `/api/profile` | read / replace the seller profile |
| POST | `/api/profile/generate` `{company?, description?}` | build the profile from decks + web pages |
| GET/POST | `/api/profile/sources` | list / upload decks (multipart `files`) |
| POST | `/api/projects/{id}/feedback` `{verdict}` | confirmed / dismissed / clear |
| POST | `/api/project-contacts/{id}/enrich` · `/feedback` | Get email / right or wrong person |
| POST/GET | `/api/people/{id}/pitch` | write / read a person's pitch |
| POST | `/api/accounts/{id}/pitches` `{limit, min_fit}` | pitch the top contacts of an account |
| GET/PUT | `/api/pitches` · `/api/pitches/{id}` | list / edit and approve |
| GET | `/api/pitches.csv?ids=1,2` | Dripify CSV |
| DELETE | `/api/profile/sources/{id}` | remove a deck or page |
| POST | `/api/profile/research` `{targets: [{name, domain}]}` | Tavily research on your own companies |
| POST/GET | `/api/profile/rescore` | re-judge fit on all accounts / progress |

## Roadmap

1. **Push to outreach:** HubSpot/Salesforce, Dripify, Apollo sequences; reply outcomes feed the
   feedback loop.
2. **Licensed job-data feed** (e.g. a jobs API) for full Naukri/LinkedIn coverage at scale.
3. **Email/Slack delivery** of alerts.
4. **Multi-tenant SaaS:** auth, workspaces, usage credits, Postgres, hosting, plus GDPR/DPDP
   controls (retention, deletion on request). Research is shared across customers; contacts
   bought and feedback stay private to each.

## Limits to know

- Results are **inferences from public data**. Check the evidence before outreach.
- Do not scrape LinkedIn directly; use licensed providers.
- Small private companies leave fewer public signals, so expect thinner results there.
