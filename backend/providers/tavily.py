"""Web search via Tavily (https://docs.tavily.com).

Reads FULL pages (include_raw_content), not just snippets, and covers:
news, job boards, the company's own careers pages, filings, engineering blogs,
vendor announcements and tech-stack mentions.
"""
import httpx

from .. import config

URL = "https://api.tavily.com/search"
MAX_DOC_CHARS = 8000

# Public job boards and applicant-tracking systems that host company job posts.
JOB_DOMAINS = [
    "naukri.com", "linkedin.com", "indeed.com", "foundit.in", "instahyre.com", "glassdoor.com",
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com", "smartrecruiters.com",
    "workable.com", "bamboohr.com", "careers-page.com",
]

# (source_type, query template, options). {c} is replaced with the company name.
QUERIES: list[tuple[str, str, dict]] = [
    # Sources that describe projects themselves
    ("case_study", '"{c}" case study OR "customer story" OR "success story" migration OR implementation OR modernisation OR transformation', {}),
    ("news", '"{c}" announces OR launches OR "went live" OR rolls out platform OR app OR programme', {"topic": "news"}),
    ("news", '"{c}" digital transformation OR modernisation OR migration programme', {"topic": "news"}),
    ("vendor", '"{c}" selects OR "partners with" OR implements OR deploys OR "goes live with"', {"topic": "news"}),
    ("filing", '"{c}" annual report OR earnings call OR "investor presentation" strategic priorities technology investment', {}),
    ("post", '"{c}" "went live" OR "excited to announce" OR "proud to share" launched OR migrated OR rebuilt', {"include_domains": ["linkedin.com"]}),
    ("blog", '"{c}" engineering blog how we built OR migrated OR scaled', {}),
    ("news", '"{c}" appoints OR names OR hires CTO OR CIO OR "chief digital officer" OR "head of"', {"topic": "news"}),
    ("deal", '"{c}" contract OR "multi-year deal" OR "signs deal" OR awarded OR "strategic partnership" OR outsourcing IT services OR technology', {"topic": "news"}),
    ("footprint", '"{c}" offices OR "R&D centre" OR "engineering centre" OR "global capability centre" OR "development center" OR "innovation hub" opens OR expands', {}),
    # Projects: named engagements with a specific client or partner
    ("project", '"{c}" wins OR bags OR secures OR signs deal OR contract OR mandate OR engagement client', {"topic": "news"}),
    ("project", '"{c}" "selected by" OR "chosen by" OR "engaged by" OR "awarded" to implement OR modernise OR build OR transform', {"topic": "news"}),
    ("project", '"{c}" client project delivered OR implemented OR built for case study', {}),
    # Supporting evidence: hiring and tech
    ("jobs", '"{c}" jobs hiring engineer OR QA OR SDET OR architect OR "data engineer"', {"include_domains": JOB_DOMAINS}),
    ("tech", '"{c}" uses OR "built on" OR "migrates to" AWS OR Azure OR "Google Cloud" OR Salesforce OR SAP OR Snowflake', {}),
]


def _post(body: dict) -> list[dict]:
    try:
        resp = httpx.post(URL, json=body, headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"}, timeout=60)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    return resp.json().get("results", [])


def raw_search(query: str, topic: str = "general", days: int | None = None, max_results: int = 10,
               include_domains: list[str] | None = None, full_text: bool = False,
               country: str | None = None) -> list[dict]:
    """One Tavily query. Returns [{url, title, published_at, text}].
    country (lowercase English name) boosts results from that country; Tavily only supports it for general search."""
    body = {"query": query, "search_depth": "advanced", "max_results": max_results,
            "include_raw_content": bool(full_text)}
    if topic == "news":
        body["topic"] = "news"
        if days:
            body["days"] = days
    if include_domains:
        body["include_domains"] = include_domains
    results = None
    if country and topic != "news":
        results = _post({**body, "country": country}) or None   # unknown country name → retry without it
    out = []
    for r in (results if results is not None else _post(body)):
        if not r.get("url"):
            continue
        text = (r.get("raw_content") if full_text else None) or r.get("content") or ""
        out.append({"url": r["url"], "title": r.get("title", ""), "published_at": r.get("published_date"),
                    "text": text.strip()[:MAX_DOC_CHARS]})
    return out


def search(company: str, domain: str | None = None) -> list[dict]:
    """All signal queries for one company, full page text, de-duplicated by URL."""
    first_word = company.lower().split()[0]
    seen, out = set(), []

    def add(source_type: str, results: list[dict], check_name: bool = True):
        for r in results:
            if r["url"] in seen or len(r["text"]) < 120:
                continue
            if check_name and first_word not in (r["text"] + r["title"]).lower():
                continue  # result doesn't mention the company
            seen.add(r["url"])
            out.append({"source_type": source_type, **r})

    for source_type, template, opts in QUERIES:
        add(source_type, raw_search(
            template.format(c=company), topic=opts.get("topic", "general"),
            days=config.LOOKBACK_DAYS if opts.get("topic") == "news" else None,
            max_results=config.RESULTS_PER_QUERY, include_domains=opts.get("include_domains"), full_text=True))

    if domain:  # the company's own careers pages and newsroom
        add("jobs", raw_search("careers jobs open positions engineering technology", max_results=4,
                               include_domains=[domain], full_text=True), check_name=False)
        add("news", raw_search("press release newsroom announces", max_results=4,
                               include_domains=[domain], full_text=True), check_name=False)
        add("project", raw_search("case study client success story project delivered", max_results=5,
                                  include_domains=[domain], full_text=True), check_name=False)
    return out
