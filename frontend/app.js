const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => Math.round((x || 0) * 100);
const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

const STAGES = [["hinted", "Hinted"], ["announced", "Announced"], ["hiring", "Hiring"], ["in_flight", "In flight"], ["vendor_selection", "Choosing vendors"]];
const RUN_STEPS = [["Collecting", "Reading public sources"], ["Extracting", "Finding initiatives"], ["contacts", "Mapping people"], ["Done", "Done"]];

const state = { view: "home", account: null, tab: "initiatives", detail: null, health: null, discover: { mode: "radar", preset: "qa_hiring", days: 30, hits: [], browse: null, page: 1 } };
let poller = null;

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(body.detail || body || res.statusText);
  return body;
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast"; t.setAttribute("role", "status"); t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

/* ------------------------------------------------------------------ rail */

async function loadHealth() {
  const h = (state.health = await api("/api/health"));
  $("#seller").textContent = h.seller || "…";
  const c = $("#conn");
  c.className = "conn" + (h.configured ? "" : " off");
  c.innerHTML = h.configured
    ? `<b>Connected</b> to ${h.llm_provider === "openai" ? "GPT" : "Claude"}, Tavily${h.people_search ? " and Apollo" : ""}`
    : `<b>Setup needed:</b> add ${h.missing_keys.map(esc).join(" and ")} to .env`;
}

async function loadAccounts() {
  const list = await api("/api/accounts");
  $("#acctCount").textContent = list.length || "";
  $("#accounts").innerHTML = list.map((a) => {
    const busy = a.status === "queued" || a.status === "running";
    const dot = busy ? `<span class="pulse" title="Researching"></span>` : a.status === "failed" ? `<span class="failed-dot" title="Research failed"></span>` : "";
    const meta = [a.watch ? "Watched" : "", a.industry, a.hq_country].filter(Boolean).join(", ") || a.domain || (busy ? "Researching…" : "");
    return `<li data-id="${a.id}" class="${state.view === "account" && a.id === state.account ? "active" : ""}" tabindex="0">
      <span class="a-name">${dot}${esc(a.name)}</span><span class="a-count">${a.unread ? `<span class="new" title="${a.unread} new change${a.unread > 1 ? "s" : ""}">${a.unread} new</span>` : a.initiatives || ""}</span>
      ${meta ? `<span class="a-meta">${esc(meta)}</span>` : ""}</li>`;
  }).join("") || `<li class="empty-li">Nothing researched yet.</li>`;
  $$("#accounts li[data-id]").forEach((li) => {
    li.onclick = () => openAccount(+li.dataset.id);
    li.onkeydown = (e) => e.key === "Enter" && openAccount(+li.dataset.id);
  });
  return list;
}

function setNav(view) {
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === (view === "account" ? "home" : view)));
}

/* ------------------------------------------------------------------ home */

const RADAR_MOTIF = `<svg class="motif" viewBox="0 0 240 240" aria-hidden="true"><circle cx="120" cy="120" r="118" /><circle cx="120" cy="120" r="84" /><circle cx="120" cy="120" r="50" /><circle cx="120" cy="120" r="9" class="dotc" /></svg>`;
const STAGE_LABEL = Object.fromEntries(STAGES);

async function renderHome() {
  state.view = "home"; setNav("home"); clearInterval(poller);
  const h = state.health;
  let sum = null;
  try { sum = await api("/api/summary"); } catch (e) { /* first run */ }
  const t = sum?.totals || { accounts: 0 };
  const empty = !t.accounts;

  $("#view").innerHTML = `<div class="wrap home">
    ${h && !h.configured ? setupNotice(h) : ""}
    <section class="hero home-hero">${RADAR_MOTIF}
      <h1>Find the initiative, then the person who owns it.</h1>
      <p class="lede">Job posts, news, filings, case studies and engineering blogs, turned into live initiatives, the people behind them, and a reason to reach out now.</p>
      ${empty ? "" : `<div class="tiles">
        <div class="tile"><b>${t.accounts}</b><span>accounts researched</span></div>
        <div class="tile"><b>${t.projects}</b><span>live initiatives found</span></div>
        <div class="tile"><b>${t.owners}</b><span>initiative owners identified</span></div>
        <div class="tile ${t.unread ? "hot" : ""}"><b>${t.unread}</b><span>new changes${t.watched ? `, ${t.watched} watched` : ""}</span></div>
      </div>`}
    </section>

    ${empty ? `<div class="paths">
      <button class="path" id="goResearch"><h3>Research a company you have in mind</h3>
        <p>Type its name on the left. Adding the website makes the people search much better.</p>
        <div class="eg">About a minute per company</div></button>
      <button class="path" id="goDiscover"><h3>Find companies showing a signal</h3>
        <p>Scan recent news for companies hiring testers, launching apps, migrating platforms and more.</p>
        <div class="eg">Or browse by industry, country and size</div></button>
    </div>` : `<div class="dash">
      <section class="panel-card"><div class="pc-head"><h2>Best-fit initiatives right now</h2><span class="muted small">across all accounts</span></div>
        ${sum.top_projects.length ? `<ol class="toplist">${sum.top_projects.map((p) => `<li data-open="${p.company_id}">
          <span class="ring" style="--p:${pct(p.fit_score)}"><b>${pct(p.fit_score)}</b></span>
          <div class="tl-main"><div class="tl-name">${esc(p.name)}</div>
            <div class="muted small">${esc(p.company)} · ${esc(STAGE_LABEL[p.stage] || p.stage)}${p.top_contact ? ` · ${esc(p.top_contact)}${p.top_title ? `, ${esc(p.top_title)}` : ""}` : ""}</div></div>
          ${p.basis === "hiring" ? `<span class="basis hiring">Hiring only</span>` : p.basis === "announced" ? `<span class="basis announced">Described</span>` : ""}
        </li>`).join("")}</ol>` : `<p class="muted">No initiatives yet.</p>`}
      </section>
      <aside class="dash-side">
        <section class="panel-card"><div class="pc-head"><h2>Latest changes</h2><button class="btn quiet small" id="allAlerts">See all</button></div>
          ${sum.recent_alerts.length ? `<ul class="mini-alerts">${sum.recent_alerts.map((a) => `<li data-open="${a.company_id}" data-tab="changes" class="${a.read ? "" : "unread"}">
            <span class="ma-kind k-${a.kind}"></span><div><div class="ma-title">${esc(a.title)}</div><div class="muted small">${esc(a.company)}, ${esc((a.created_at || "").slice(0, 10))}</div></div></li>`).join("")}</ul>`
            : `<p class="muted small">Watch an account weekly and changes show up here.</p>`}
        </section>
        <section class="panel-card quick"><h2>Find more</h2>
          <button class="btn primary block" id="goDiscover">Scan for signals</button>
          <button class="btn ghost block" id="goResearch">Research a company</button>
        </section>
      </aside>
    </div>`}
  </div>`;
  $("#goResearch")?.addEventListener("click", () => $("#name").focus());
  $("#goDiscover")?.addEventListener("click", () => renderDiscover());
  $("#allAlerts")?.addEventListener("click", () => renderAlerts());
  $$("[data-open]").forEach((el) => el.onclick = () => openAccount(+el.dataset.open, el.dataset.tab || "initiatives"));
  loadAccounts();
}

function setupNotice(h) {
  return `<div class="notice">To research companies, add ${h.missing_keys.map(esc).join(" and ")} to the <code>.env</code> file and restart the app.</div>`;
}

/* ------------------------------------------------------------------ account */

const ALERT_LABEL = { new_initiative: "New initiative", stage_change: "Stage change", new_leader: "New leader", hiring_surge: "Hiring surge", new_vendor: "New vendor" };
const SOURCE_LABEL = { jobs: "job posts", news: "news articles", vendor: "vendor announcements", filing: "filings and reports", blog: "engineering blogs", tech: "tech mentions", case_study: "case studies", post: "public posts", deal: "deal news", footprint: "location news" };

async function openAccount(id, tab = "initiatives") {
  state.view = "account"; state.account = id; state.tab = tab; setNav("account");
  clearInterval(poller);
  await loadAccounts();
  await renderAccount();
  window.scrollTo(0, 0);
  $("#view").focus({ preventScroll: true });
}

function runStepIndex(log) {
  const text = log.join("\n");
  if (/Done$/m.test(text)) return 3;
  if (/contacts, fit/.test(text)) return 2;
  if (/Extracting/.test(text)) return 1;
  return 0;
}

async function renderAccount() {
  const d = await api(`/api/accounts/${state.account}`);
  state.detail = d;
  const c = d.company, run = d.run;
  const busy = run && (run.status === "queued" || run.status === "running");
  const people = d.initiatives.reduce((n, i) => n + i.contacts.filter((x) => x.feedback !== "rejected").length, 0);
  const owners = d.initiatives.reduce((n, i) => n + i.contacts.filter((x) => x.role === "Owner" && x.feedback !== "rejected").length, 0);
  const named = d.initiatives.reduce((n, i) => n + i.contacts.filter((x) => x.source === "evidence").length, 0);
  const step = busy ? runStepIndex(run.log) : -1;
  const mix = Object.entries(d.source_mix || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${SOURCE_LABEL[k] || k}`).join(", ");

  const facts = [
    c.industry && `<span class="fact">${esc(c.industry)}</span>`,
    c.hq_country && `<span class="fact">${esc(c.hq_country)}</span>`,
    c.domain && `<a class="fact" href="https://${esc(c.domain)}" target="_blank" rel="noopener">${esc(c.domain)}</a>`,
  ].filter(Boolean).join("");
  const tabs = [["initiatives", "Initiatives"], ["org", "Org chart"], ["footprint", "Footprint"], ["tech", "Vendors & deals"], ["changes", `Changes${d.unread_alerts ? ` <span class="badge">${d.unread_alerts}</span>` : ""}`]];

  $("#view").innerHTML = `<div class="wrap">
    <section class="hero acct-hero">${RADAR_MOTIF}
    <div class="dossier">
      <div><h1>${esc(c.name)}</h1>${facts ? `<div class="facts">${facts}</div>` : ""}
        ${c.summary ? `<p class="about">${esc(c.summary)}</p>` : ""}</div>
      <div class="acct-actions">
        <button class="btn ${c.watch ? "watching" : "ghost"}" id="watch" aria-pressed="${!!c.watch}" title="Re-research every ${d.watch_every_days} days and alert you to changes">${c.watch ? "Watching weekly" : "Watch weekly"}</button>
        <button class="btn ghost" id="refresh" ${busy ? "disabled" : ""} title="Search the web again and rebuild everything">${busy ? "Researching…" : "Research again"}</button>
        <a class="btn ghost" href="/api/accounts/${c.id}/export.csv">Export CSV</a>
        <button class="btn quiet" id="del">Delete</button>
      </div>
    </div>
    ${d.initiatives.length ? `<div class="tiles">
      <div class="tile"><b>${d.initiatives.length}</b><span>initiatives</span></div>
      <div class="tile"><b>${owners}</b><span>likely owners</span></div>
      <div class="tile"><b>${named}</b><span>named in sources</span></div>
      <div class="tile"><b>${people}</b><span>contacts</span></div>
      <div class="tile"><b>${d.documents}</b><span>pages read</span></div></div>` : ""}
    ${mix ? `<p class="mix">Read ${esc(mix)}.${c.last_researched_at ? ` Last researched ${esc(c.last_researched_at.slice(0, 10))}.` : ""}</p>` : ""}
    </section>
    ${busy ? `<div class="progress" aria-live="polite"><h3>Researching ${esc(c.name)}</h3>
      <div class="steps">${RUN_STEPS.map(([, label], i) => `<div class="step ${i < step ? "done" : i === step ? "now" : ""}">${label}</div>`).join("")}</div>
      <ul class="log">${run.log.slice(-6).map((l) => `<li>${esc(l.trim())}</li>`).join("")}</ul></div>` : ""}
    ${run && run.status === "failed" ? `<div class="notice">${esc(run.error)}</div>` : ""}
    <div class="tabs" role="tablist">${tabs.map(([k, label]) => `<button role="tab" data-tab="${k}" class="${state.tab === k ? "on" : ""}">${label}</button>`).join("")}</div>
    <div id="tabBody"></div>
  </div>`;

  $$(".tabs button").forEach((b) => b.onclick = () => { state.tab = b.dataset.tab; $$(".tabs button").forEach((x) => x.classList.toggle("on", x === b)); drawTab(); });
  $("#watch").onclick = async () => {
    const r = await api(`/api/accounts/${c.id}/watch`, { method: "POST", body: JSON.stringify({ watch: !c.watch }) });
    toast(r.watch ? `Watching ${c.name}: re-checked every ${r.every_days} days while the app is running` : `Stopped watching ${c.name}`);
    renderAccount(); loadAccounts();
  };
  $("#refresh").onclick = async () => { try { await api(`/api/accounts/${c.id}/refresh?force=true`, { method: "POST" }); renderAccount(); poll(); } catch (e) { toast(e.message); } };
  $("#del").onclick = async () => {
    if (!confirm(`Delete ${c.name} and all its research?`)) return;
    await api(`/api/accounts/${c.id}`, { method: "DELETE" });
    toast(`Deleted ${c.name}`); renderHome();
  };
  drawTab();
  if (busy) poll();
}

function drawTab() {
  const t = state.tab;
  if (t === "org") return drawOrg();
  if (t === "tech") return drawTech();
  if (t === "footprint") return drawFootprint();
  if (t === "changes") return drawChanges();
  drawInitiatives();
}

/* ---------- initiatives tab */

function drawInitiatives() {
  const d = state.detail, run = d.run;
  const busy = run && (run.status === "queued" || run.status === "running");
  $("#tabBody").innerHTML = `
    ${d.initiatives.length ? `<div class="board-head"><span class="muted small">Best fit first, scored against what ${esc(state.health?.seller || "you")} sells. Mark contacts right or wrong and future research learns from it.</span>
      ${d.dismissed ? `<span class="muted small">${d.dismissed} dismissed initiative${d.dismissed > 1 ? "s" : ""} hidden</span>` : ""}</div>` : ""}
    ${d.initiatives.map(initiative).join("")}
    ${!busy && run?.status === "done" && !d.initiatives.length ? `<div class="blank"><h3>No initiatives found in public sources</h3><p>Add the company's website on the left and research again, or try a more specific company name.</p></div>` : ""}`;
  $$("[data-copy]").forEach((b) => b.onclick = () => { navigator.clipboard?.writeText(b.dataset.copy); toast("Opener copied"); });
  $$("[data-enrich]").forEach((b) => b.onclick = () => enrich(b));
  $$("[data-brief]").forEach((b) => b.onclick = () => openBrief(b));
  $$("[data-verdict]").forEach((b) => b.onclick = async () => {
    await api(`/api/contacts/${b.dataset.id}/feedback`, { method: "POST", body: JSON.stringify({ verdict: b.dataset.verdict }) });
    toast(b.dataset.verdict === "confirmed" ? "Marked as the right person" : b.dataset.verdict === "rejected" ? "Won't be suggested again for this kind of initiative" : "Verdict cleared");
    renderAccount();
  });
  $$("[data-dismiss]").forEach((b) => b.onclick = async () => {
    await api(`/api/initiatives/${b.dataset.dismiss}/feedback`, { method: "POST", body: JSON.stringify({ verdict: "dismissed" }) });
    toast("Dismissed. Future research of this company will skip it.");
    renderAccount();
  });
  $$("[data-confirm-init]").forEach((b) => b.onclick = async () => {
    const on = b.getAttribute("aria-pressed") === "true";
    await api(`/api/initiatives/${b.dataset.confirmInit}/feedback`, { method: "POST", body: JSON.stringify({ verdict: on ? "clear" : "confirmed" }) });
    renderAccount();
  });
}

function initiative(i) {
  const idx = Math.max(0, STAGES.findIndex(([k]) => k === i.stage));
  const track = `<div class="track" aria-label="Stage: ${esc(STAGES[idx][1])}">
    <span class="bar" style="width:${idx * 25}%"></span>
    ${STAGES.map(([, label], n) => `<div class="t-step ${n < idx ? "past" : n === idx ? "now" : ""}" style="left:${n * 25}%">${label}</div>`).join("")}</div>`;
  const live = i.contacts.filter((p) => p.feedback !== "rejected");
  const rejected = i.contacts.filter((p) => p.feedback === "rejected");
  const sources = i.evidence.map((e) => `<li><q>${esc(e.quote)}</q>
      <span class="src">${esc(e.published_at || "Undated")}, ${esc(SOURCE_LABEL[e.source_type] || e.source_type)}: <a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title || e.url)}</a></span></li>`).join("");
  const confirmed = i.feedback === "confirmed";
  return `<article class="initiative ${confirmed ? "is-confirmed" : ""} b-${esc(i.basis || "none")}">
    <div class="i-top">
      <div><div class="i-cat">${esc(i.category_label)}
          ${i.basis === "hiring" ? `<span class="basis hiring" title="Only job posts point to this initiative so far. Treat it as a lead to verify.">Inferred from hiring only</span>`
            : i.basis === "announced" ? `<span class="basis announced" title="Described in news, a case study, a filing or a public post">Publicly described</span>` : ""}
          ${confirmed ? ` <span class="ok">Confirmed by your team</span>` : ""}</div><h3>${esc(i.name)}</h3></div>
      <div class="fit ${i.fit_score < 0.5 ? "low" : ""}"><span class="ring big" style="--p:${pct(i.fit_score)}"><b>${pct(i.fit_score)}<small>%</small></b></span>
        <div class="fit-why"><b>Fit for Moolya</b>${esc(i.fit_reason)}</div></div>
    </div>
    ${track}
    <p class="i-summary">${esc(i.summary)}</p>
    <div class="i-meta">${i.tech.slice(0, 8).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}
      <span class="conf">${pct(i.confidence)}% confidence${i.last_seen ? `, latest signal ${esc(i.last_seen)}` : ""}</span></div>
    <div class="people">${live.map(person).join("") || `<p class="muted small" style="padding-top:12px">No people found yet. Add the company's website and research again so the people search can run.</p>`}</div>
    ${rejected.length ? `<details class="rejected"><summary>${rejected.length} contact${rejected.length > 1 ? "s" : ""} you marked as wrong</summary>${rejected.map(person).join("")}</details>` : ""}
    <div class="i-foot">
      <details class="sources"><summary>Show the ${i.evidence.length} source${i.evidence.length === 1 ? "" : "s"} behind this</summary><ul class="source-list">${sources}</ul></details>
      <div class="i-verdict">
        <button class="btn quiet small" data-confirm-init="${i.id}" aria-pressed="${confirmed}">${confirmed ? "Undo confirm" : "This is real"}</button>
        <button class="btn quiet small" data-dismiss="${i.id}">Not relevant</button>
      </div>
    </div>
  </article>`;
}

function person(p) {
  const contact = [p.email && `<a href="mailto:${esc(p.email)}">${esc(p.email)}</a>`, p.linkedin_url && `<a href="${esc(p.linkedin_url)}" target="_blank" rel="noopener">LinkedIn</a>`].filter(Boolean).join(" &nbsp; ");
  const v = p.feedback;
  return `<div class="person r-${p.role} ${v ? "v-" + v : ""}">
    <div class="avatar" aria-hidden="true">${esc(initials(p.full_name))}</div>
    <div><div class="p-name">${esc(p.full_name)}${v === "confirmed" ? ` <span class="ok">Confirmed</span>` : ""}</div><div class="p-title">${esc(p.title)}</div><span class="p-role">${p.role}</span>
      ${p.full_name.includes("*") && !p.email ? `<div class="masked">Surname hidden until you click Get email (uses 1 Apollo credit)</div>` : ""}</div>
    <div><div class="p-why">${esc(p.rationale)}</div>
      <div class="p-src">${p.source === "evidence" ? `<span class="named">Named in sources</span>` : `<span>From people database</span>`}
        <span><span class="meter"><i style="width:${pct(p.score)}%"></i></span> ${pct(p.score)}%</span></div>
      ${contact ? `<div class="p-contact">${contact}</div>` : ""}</div>
    <div class="p-actions">
      <button class="btn ghost small" data-brief="${p.person_id}" data-has="${p.has_brief ? 1 : 0}">${p.has_brief ? "View brief" : "Buyer brief"}</button>
      <button class="btn ghost small" data-copy="${esc(p.opener)}" title="${esc(p.opener)}">Copy opener</button>
      ${p.email ? "" : `<button class="btn ghost small" data-enrich="${p.id}">Get email</button>`}
      <span class="verdict">
        ${v ? `<button class="btn quiet small" data-verdict="clear" data-id="${p.id}">Undo</button>`
            : `<button class="btn quiet small yes" data-verdict="confirmed" data-id="${p.id}" title="This is the right person">Right person</button>
               <button class="btn quiet small no" data-verdict="rejected" data-id="${p.id}" title="Wrong person; don't suggest again">Wrong</button>`}
      </span>
    </div></div>
    <div class="brief-slot" id="brief-${p.person_id}-${p.id}"></div>`;
}

const STYLE_LABEL = { "data-driven": "Data-driven", visionary: "Visionary", pragmatic: "Pragmatic", technical: "Technical", "relationship-led": "Relationship-led", unknown: "Not enough to tell" };

async function openBrief(btn, force = false) {
  const slot = btn.closest(".person").nextElementSibling;
  if (slot.innerHTML && !force) { slot.innerHTML = ""; return; }
  const pid = btn.dataset.brief;
  slot.innerHTML = `<div class="brief loading"><div class="radar"></div>Reading what they've said publicly…</div>`;
  try {
    const b = btn.dataset.has === "1" && !force ? await api(`/api/people/${pid}/brief`) : await api(`/api/people/${pid}/brief${force ? "?force=true" : ""}`, { method: "POST" });
    btn.dataset.has = "1"; btn.textContent = "View brief";
    slot.innerHTML = renderBrief(b, pid);
    $(".refresh-brief", slot)?.addEventListener("click", () => openBrief(btn, true));
  } catch (e) { slot.innerHTML = `<div class="brief"><p class="notice">${esc(e.message)}</p></div>`; }
}

function renderBrief(b, pid) {
  const list = (title, items) => items?.length ? `<div><h4>${title}</h4><ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
  const src = (n) => b.sources?.find((x) => x.n === n);
  return `<div class="brief">
    <div class="brief-head"><div><span class="style-chip">${esc(STYLE_LABEL[b.communication_style] || b.communication_style || "")}</span>
      <span class="conf-chip c-${esc(b.confidence)}">${esc(b.confidence || "")} confidence</span></div>
      <button class="btn quiet small refresh-brief">Refresh</button></div>
    <p class="brief-sum">${esc(b.summary || "")}</p>
    ${b.style_note ? `<p class="muted small">${esc(b.style_note)}</p>` : ""}
    ${b.note ? `<p class="muted small">${esc(b.note)}</p>` : ""}
    <div class="brief-grid">
      ${list("What they focus on", b.priorities)}${list("What drives them", b.motivators)}
      ${list("What worries them", b.concerns)}${list("How to open", b.approach)}
      ${list("Avoid", b.avoid)}${list("Link to what you sell", b.talking_points)}
    </div>
    ${b.evidence?.length ? `<h4>In their words</h4><ul class="source-list">${b.evidence.map((e) => { const s = src(e.source); return `<li><q>${esc(e.quote)}</q>
      ${s ? `<span class="src">${esc(s.published_at || "")} <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a></span>` : ""}</li>`; }).join("")}</ul>` : ""}
    <p class="muted small">Built from ${b.sources?.length || 0} public source${b.sources?.length === 1 ? "" : "s"} on ${esc((b.created_at || "").slice(0, 10))}. Professional statements only.</p>
  </div>`;
}

/* ---------- footprint tab */

const LOC_TYPE = { hq: "Headquarters", office: "Office", rd_centre: "R&D centre", engineering_centre: "Engineering centre", gcc: "Global capability centre", delivery_centre: "Delivery centre", plant: "Plant", other: "Site" };

async function drawFootprint() {
  const f = await api(`/api/accounts/${state.account}/footprint`);
  const max = Math.max(1, ...f.hiring.map((h) => h.roles));
  $("#tabBody").innerHTML = `
    <section class="sect"><h2>Sites</h2>
      <p class="muted small">Headquarters, offices, R&amp;D and engineering centres, GCCs and plants mentioned in the sources.</p>
      ${f.sites.length ? `<table class="grid"><thead><tr><th>Location</th><th>Type</th><th>What happens there</th><th>People</th><th>Source</th></tr></thead><tbody>
        ${f.sites.map((x) => `<tr><td><b>${esc([x.city, x.country].filter(Boolean).join(", "))}</b></td><td>${esc(LOC_TYPE[x.type] || x.type)}</td>
          <td>${x.functions.map((fn) => `<span class="tag">${esc(fn)}</span>`).join(" ")}</td><td>${x.headcount ? x.headcount.toLocaleString() : ""}</td>
          <td class="small">${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.doc_title || "Source")}</a>` : ""}${x.quote ? `<div class="muted">“${esc(x.quote)}”</div>` : ""}</td></tr>`).join("")}
      </tbody></table>` : `<p class="blank-line">No sites mentioned in the sources yet.</p>`}
    </section>
    <section class="sect"><h2>Where they're hiring</h2>
      <p class="muted small">Open roles by city, from the job posts read. Hiring clusters often point to where an initiative's team sits.</p>
      ${f.hiring.length ? `<div class="bars">${f.hiring.map((h) => `<div class="bar-row"><span class="b-city">${esc(h.city)}${h.country ? `<span class="muted">, ${esc(h.country)}</span>` : ""}</span>
        <span class="b-track"><i style="width:${(h.roles / max) * 100}%"></i></span><span class="b-n">${h.roles}</span>
        <span class="b-fn muted small">${esc(h.functions.join(", "))}</span></div>`).join("")}</div>` : `<p class="blank-line">No job posts with locations yet.</p>`}
    </section>`;
}

/* ---------- org chart tab */

async function drawOrg() {
  $("#tabBody").innerHTML = `<div class="scanning"><div class="radar"></div>Drawing the org chart…</div>`;
  const o = await api(`/api/accounts/${state.account}/org`);
  if (!o.nodes.length) { $("#tabBody").innerHTML = `<div class="blank"><h3>No people found yet</h3><p>The org chart fills in from people named in sources and, with an Apollo key and the company's website, from its leadership team.</p></div>`; return; }
  const byId = Object.fromEntries(o.nodes.map((n) => [n.id, n]));
  const kids = {}; const hasParent = new Set();
  o.edges.forEach((e) => { (kids[e.from] ||= []).push(e); hasParent.add(e.to); });
  const roots = o.nodes.filter((n) => !hasParent.has(n.id));
  const inits = [...new Map(o.nodes.flatMap((n) => n.initiatives).map((i) => [i.id, i])).values()];

  const card = (n) => {
    const roles = n.initiatives.map((i) => `<span class="mini r-${i.role}" data-init="${i.id}">${i.role} · ${esc(i.name)}</span>`).join("");
    return `<div class="onode" data-inits="${n.initiatives.map((i) => i.id).join(",")}">
      <div class="avatar small" aria-hidden="true">${esc(initials(n.name))}</div>
      <div><div class="p-name">${esc(n.name)}</div><div class="p-title">${esc(n.title || "")}</div>
        <div class="o-meta"><span class="fn">${esc(n.function)}</span>${n.source === "evidence" ? `<span class="named">named in sources</span>` : ""}${n.linkedin_url ? `<a href="${esc(n.linkedin_url)}" target="_blank" rel="noopener">LinkedIn</a>` : ""}</div>
        ${roles ? `<div class="o-roles">${roles}</div>` : ""}</div></div>`;
  };
  const tree = (n, kind) => `<li class="e-${kind || "root"}">${card(n)}${(kids[n.id] || []).length
      ? `<ul>${kids[n.id].sort((a, b) => byId[a.to].rank - byId[b.to].rank).map((e) => tree(byId[e.to], e.kind)).join("")}</ul>` : ""}</li>`;

  $("#tabBody").innerHTML = `<div class="org-head">
      <p class="muted small">${o.nodes.length} people. <b class="solid">${o.confirmed}</b> reporting line${o.confirmed === 1 ? "" : "s"} confirmed by a source, <b class="dashed">${o.inferred}</b> inferred from titles and seniority.</p>
      ${inits.length ? `<label class="hl">Highlight people on <select id="hlSel"><option value="">all initiatives</option>${inits.map((i) => `<option value="${i.id}">${esc(i.name)}</option>`).join("")}</select></label>` : ""}
    </div>
    <div class="legend"><span><i class="ln solid"></i>confirmed reporting line</span><span><i class="ln dashed"></i>inferred</span>
      <span><i class="dot r-Owner"></i>owner</span><span><i class="dot r-Sponsor"></i>sponsor</span><span><i class="dot r-Influencer"></i>influencer</span><span><i class="dot r-Practitioner"></i>practitioner</span></div>
    <ul class="org">${roots.sort((a, b) => a.rank - b.rank).map((r) => tree(r)).join("")}</ul>`;
  $("#hlSel")?.addEventListener("change", (e) => {
    const id = e.target.value;
    $$(".onode").forEach((el) => el.classList.toggle("dim", !!id && !el.dataset.inits.split(",").includes(id)));
    $$(".mini").forEach((el) => el.classList.toggle("dim", !!id && el.dataset.init !== id));
  });
}

/* ---------- tech & vendors tab */

async function drawTech() {
  const t = await api(`/api/accounts/${state.account}/tech`);
  const onSite = (x) => x.source === "website" || x.source === "builtwith";
  const fromSources = t.tech.filter((x) => !onSite(x));
  const fromSite = t.tech.filter(onSite);
  const rel = { selected: "Selected", partner: "Partner", incumbent: "Current vendor", replacing: "Being replaced", evaluating: "Evaluating" };
  const dt = { new: "New deal", renewal: "Renewal", expansion: "Expansion", ended: "Ended" };
  $("#tabBody").innerHTML = `
    <section class="sect"><h2>Deal history</h2>
      <p class="muted small">Who they've bought from and when, newest first, from announcements, vendor press releases and case studies.${state.health?.seller ? ` Competitors listed in your profile are flagged.` : ""}</p>
      ${t.vendors.length ? `<table class="grid deals"><thead><tr><th>When</th><th>Vendor</th><th>What for</th><th>Deal</th><th>Value</th><th>Source</th></tr></thead><tbody>
        ${t.vendors.map((v) => `<tr class="${v.is_competitor ? "comp" : ""}"><td class="when">${esc(v.deal_date || v.published_at || "")}</td>
          <td><b>${esc(v.name)}</b>${v.is_competitor ? ` <span class="warn">Competitor</span>` : ""}<div class="muted small">${esc(rel[v.relationship] || v.relationship || "")}</div></td>
          <td>${esc(v.area || "")}</td>
          <td>${v.deal_type ? `<span class="deal d-${esc(v.deal_type)}">${esc(dt[v.deal_type])}</span>` : ""}${v.duration ? `<div class="muted small">${esc(v.duration)}</div>` : ""}</td>
          <td>${esc(v.deal_value || "")}</td>
          <td class="small">${v.url ? `<a href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.doc_title || "Source")}</a>` : ""}${v.quote ? `<div class="muted">“${esc(v.quote)}”</div>` : ""}</td></tr>`).join("")}
      </tbody></table>` : `<p class="blank-line">No vendor deals mentioned in the sources yet.</p>`}
    </section>
    <section class="sect"><h2>Tech stack</h2>
      <p class="muted small">From job posts, engineering blogs and news, plus what their website runs (detected from its code).</p>
      ${fromSources.length ? `<div class="stack">${fromSources.map((x) => x.url ? `<a class="tag" href="${esc(x.url)}" target="_blank" rel="noopener" title="Seen in ${esc(SOURCE_LABEL[x.source] || x.source)}">${esc(x.name)}</a>` : `<span class="tag">${esc(x.name)}</span>`).join("")}</div>` : `<p class="blank-line">No technologies mentioned yet.</p>`}
      ${fromSite.length ? `<h3 class="sub">On their website</h3><div class="site-tech">${siteTechGroups(fromSite)}</div>`
        : `<p class="muted small">No website technologies detected yet. Add the company's website and research again.</p>`}
    </section>`;
}

function siteTechGroups(list) {
  const groups = {};
  list.forEach((x) => (groups[(x.category || "Other").split(", ")[0]] ||= []).push(x.name));
  return Object.entries(groups).sort().map(([cat, names]) =>
    `<div class="tg"><span class="tg-cat">${esc(cat)}</span><span class="stack">${names.map((n) => `<span class="tag">${esc(n)}</span>`).join("")}</span></div>`).join("");
}

/* ---------- changes tab */

async function drawChanges() {
  const r = await api(`/api/alerts?company_id=${state.account}`);
  const c = state.detail.company;
  $("#tabBody").innerHTML = r.alerts.length ? `<ul class="alerts">${r.alerts.map(alertRow).join("")}</ul>`
    : `<div class="blank"><h3>No changes yet</h3><p>${c.watch ? `${esc(c.name)} is re-checked every ${state.detail.watch_every_days} days. New initiatives, stage changes, new leaders, hiring surges and new vendors will show up here.`
        : `Turn on <b>Watch weekly</b> and ${esc(c.name)} is re-checked every ${state.detail.watch_every_days} days. Anything new shows up here.`}</p></div>`;
  if (r.alerts.some((a) => !a.read)) { await api("/api/alerts/read", { method: "POST", body: JSON.stringify({ company_id: state.account }) }); updateAlertBadge(); loadAccounts(); }
}

function alertRow(a, withCompany) {
  return `<li class="alert k-${a.kind} ${a.read ? "" : "unread"}" ${withCompany ? `data-open="${a.company_id}"` : ""}>
    <span class="a-kind">${ALERT_LABEL[a.kind] || a.kind}</span>
    <div><div class="a-title">${withCompany ? `<b>${esc(a.company)}</b>: ` : ""}${esc(a.title)}</div>${a.detail ? `<div class="muted small">${esc(a.detail)}</div>` : ""}</div>
    <span class="muted small">${esc((a.created_at || "").slice(0, 10))}</span></li>`;
}

/* ---------- global alerts view */

async function renderAlerts() {
  state.view = "alerts"; setNav("alerts"); clearInterval(poller);
  const r = await api("/api/alerts");
  $("#view").innerHTML = `<div class="wrap">
    <div class="disc-head"><h1>Changes at your accounts</h1>
      <p>Watched accounts are re-checked every week while the app is running. New initiatives, stage changes, new leaders, hiring surges and new vendors show up here.</p></div>
    ${r.unread ? `<button class="btn ghost" id="readAll">Mark all as read</button>` : ""}
    ${r.alerts.length ? `<ul class="alerts big">${r.alerts.map((a) => alertRow(a, true)).join("")}</ul>`
      : `<div class="blank"><h3>Nothing yet</h3><p>Open an account and click <b>Watch weekly</b>. Changes will appear here after its next check.</p></div>`}</div>`;
  $("#readAll")?.addEventListener("click", async () => { await api("/api/alerts/read", { method: "POST", body: "{}" }); renderAlerts(); updateAlertBadge(); loadAccounts(); });
  $$(".alert[data-open]").forEach((li) => li.onclick = () => openAccount(+li.dataset.open, "changes"));
  loadAccounts();
}

async function updateAlertBadge() {
  const r = await api("/api/alerts?unread=true");
  const b = $("#alertBadge");
  b.textContent = r.unread || ""; b.hidden = !r.unread;
}

async function enrich(btn) {
  btn.disabled = true; btn.textContent = "Looking up…";
  try { await api(`/api/contacts/${btn.dataset.enrich}/enrich`, { method: "POST" }); await renderAccount(); }
  catch (e) { toast(e.message); btn.disabled = false; btn.textContent = "Get email"; }
}

function poll() {
  clearInterval(poller);
  poller = setInterval(async () => {
    if (state.view !== "account") return clearInterval(poller);
    const d = await api(`/api/accounts/${state.account}`);
    if (!d.run || !["queued", "running"].includes(d.run.status)) { clearInterval(poller); loadAccounts(); updateAlertBadge(); }
    renderAccount();
  }, 2000);
}

/* ------------------------------------------------------------------ discover */

async function renderDiscover() {
  state.view = "discover"; setNav("discover"); clearInterval(poller);
  if (!state.options) state.options = await api("/api/discover/options");
  const o = state.options, D = state.discover, h = state.health;
  $("#view").innerHTML = `<div class="wrap">
    ${h && !h.configured ? setupNotice(h) : ""}
    <div class="disc-head"><h1>Discover companies</h1>
      <p>Start from a signal to find companies that need help right now, or browse a market by industry, country and size. Tick the ones you want and research them in one go.</p></div>
    <div class="seg" role="tablist">
      <button role="tab" data-mode="radar" class="${D.mode === "radar" ? "on" : ""}">Signal radar</button>
      <button role="tab" data-mode="browse" class="${D.mode === "browse" ? "on" : ""}">Browse by filters</button>
    </div>
    <div id="discBody"></div></div>`;
  $$(".seg button").forEach((b) => b.onclick = () => { D.mode = b.dataset.mode; renderDiscover(); });
  D.mode === "radar" ? renderRadar() : renderBrowse();
  loadAccounts();
}

function renderRadar() {
  const o = state.options, D = state.discover;
  $("#discBody").innerHTML = `<form class="panel" id="radarForm">
      <label>What should the company be doing?</label>
      <div class="chips">${o.presets.map((p) => `<button type="button" class="chip ${D.preset === p.id ? "on" : ""}" data-p="${p.id}">${esc(p.label)}</button>`).join("")}</div>
      <div class="fields">
        <div><label for="rq">Or describe your own signal</label><input id="rq" value="${esc(D.query || "")}" placeholder="e.g. insurers launching customer portals" /></div>
        <div><label for="rr">Region</label><input id="rr" list="regions" value="${esc(D.region ?? "India")}" placeholder="Any" />
          <datalist id="regions"><option>India</option><option>United States</option><option>United Kingdom</option><option>UAE</option><option>Singapore</option><option>Germany</option><option>Australia</option><option>Any</option></datalist></div>
        <div><label for="rd">News from the last</label><select id="rd">${[7, 30, 90].map((n) => `<option value="${n}" ${D.days == n ? "selected" : ""}>${n} days</option>`).join("")}</select></div>
        <button class="btn primary" type="submit">Scan</button>
      </div></form>
    <div class="results" id="hits"></div>`;
  $$(".chip").forEach((c) => c.onclick = () => { D.preset = c.dataset.p; D.query = ""; $("#rq").value = ""; $$(".chip").forEach((x) => x.classList.toggle("on", x === c)); });
  $("#rq").oninput = (e) => { D.query = e.target.value; if (D.query) { D.preset = null; $$(".chip").forEach((x) => x.classList.remove("on")); } };
  $("#radarForm").onsubmit = async (e) => {
    e.preventDefault();
    D.region = $("#rr").value.trim(); D.days = +$("#rd").value;
    $("#hits").innerHTML = `<div class="scanning"><div class="radar"></div>Reading recent news and job posts…</div>`;
    try {
      const r = await api("/api/discover/signals", { method: "POST", body: JSON.stringify({ preset: D.preset, query: D.query, region: D.region, days: D.days }) });
      D.hits = r.companies; drawHits();
    } catch (err) { $("#hits").innerHTML = `<div class="notice">${esc(err.message)}</div>`; }
  };
  if (D.hits.length) drawHits();
}

function drawHits() {
  const hits = state.discover.hits;
  if (!hits.length) { $("#hits").innerHTML = `<div class="blank"><h3>No companies found for that signal</h3><p>Try a wider region, a longer time window, or describe the signal in your own words.</p></div>`; return; }
  $("#hits").innerHTML = `<div class="results-head"><h2>${hits.length} companies showing this signal</h2>
      <button class="btn quiet" id="selAll">Select all new</button></div>
    ${hits.map((h, i) => `<label class="hit">
      <input type="checkbox" data-i="${i}" ${h.account_id ? "disabled" : ""} />
      <div><div class="hit-name">${esc(h.name)}<span>${esc([h.country, h.domain].filter(Boolean).join(", "))}</span></div>
        <div class="hit-signal">${esc(h.signal)}</div>
        ${h.source_url ? `<div class="hit-src">${esc(h.published_at || "")} <a href="${esc(h.source_url)}" target="_blank" rel="noopener">${esc(h.source_title || "Source")}</a></div>` : ""}</div>
      ${h.account_id ? `<a class="have" href="#" data-open="${h.account_id}">Already researched</a>` : "<span></span>"}
    </label>`).join("")}`;
  $("#selAll").onclick = () => { $$("#hits input:not(:disabled)").forEach((c) => c.checked = true); tray(); };
  $$("#hits input").forEach((c) => c.onchange = tray);
  $$("[data-open]").forEach((a) => a.onclick = (e) => { e.preventDefault(); openAccount(+a.dataset.open); });
  tray();
}

function renderBrowse() {
  const o = state.options, D = state.discover;
  $("#discBody").innerHTML = `<form class="panel" id="browseForm">
      ${o.browse ? "" : `<div class="notice">Browsing needs APOLLO_API_KEY in .env. The signal radar works without it.</div>`}
      <div class="fields three">
        <div><label for="bk">Industry or keywords, comma separated</label><input id="bk" value="${esc(D.kw || "")}" placeholder="e.g. banking, fintech" /></div>
        <div><label for="bl">Country or city</label><input id="bl" value="${esc(D.loc || "")}" placeholder="e.g. India" /></div>
        <div><label for="bs">Employees</label><select id="bs"><option value="">Any size</option>${o.sizes.map((s) => `<option ${D.size === s ? "selected" : ""}>${s}</option>`).join("")}</select></div>
        <button class="btn primary" type="submit" ${o.browse ? "" : "disabled"}>Search</button>
      </div>
      <p class="muted small" style="margin:10px 0 0">Company search may use Apollo credits, depending on your plan.</p></form>
    <div class="results" id="browseRes"></div>`;
  $("#browseForm").onsubmit = (e) => { e.preventDefault(); D.kw = $("#bk").value; D.loc = $("#bl").value; D.size = $("#bs").value; D.page = 1; browse(); };
  if (D.browse) drawBrowse();
}

async function browse() {
  const D = state.discover;
  $("#browseRes").innerHTML = `<div class="scanning"><div class="radar"></div>Searching companies…</div>`;
  try {
    D.browse = await api("/api/discover/companies", { method: "POST", body: JSON.stringify({ keywords: D.kw, location: D.loc, size: D.size, page: D.page }) });
    drawBrowse();
  } catch (err) { $("#browseRes").innerHTML = `<div class="notice">${esc(err.message)}</div>`; }
}

function drawBrowse() {
  const D = state.discover, b = D.browse;
  if (!b.companies.length) { $("#browseRes").innerHTML = `<div class="blank"><h3>No companies match those filters</h3><p>Try fewer keywords or a wider location.</p></div>`; return; }
  $("#browseRes").innerHTML = `<div class="results-head"><h2>${b.total ? b.total.toLocaleString() + " companies" : "Companies"}</h2>
      <button class="btn quiet" id="selAll">Select all on this page</button></div>
    <table class="grid"><thead><tr><th></th><th>Company</th><th>Industry</th><th>Employees</th><th>Location</th><th></th></tr></thead><tbody>
    ${b.companies.map((c, i) => `<tr><td><input type="checkbox" data-b="${i}" ${c.account_id ? "disabled" : ""} aria-label="Select ${esc(c.name)}" /></td>
      <td><b>${esc(c.name)}</b><div class="muted small">${esc(c.domain || "")}</div></td>
      <td>${esc(c.industry || "")}</td><td>${c.employees ? Number(c.employees).toLocaleString() : ""}</td>
      <td>${esc([c.city, c.country].filter(Boolean).join(", "))}</td>
      <td>${c.account_id ? `<a class="have" href="#" data-open="${c.account_id}">Already researched</a>` : ""}</td></tr>`).join("")}
    </tbody></table>
    <div class="pager">Page ${b.page}${b.total_pages ? ` of ${b.total_pages}` : ""}
      <button class="btn ghost small" id="prev" ${b.page <= 1 ? "disabled" : ""}>Previous</button>
      <button class="btn ghost small" id="next" ${b.total_pages && b.page >= b.total_pages ? "disabled" : ""}>Next</button></div>`;
  $("#selAll").onclick = () => { $$("#browseRes input:not(:disabled)").forEach((c) => c.checked = true); tray(); };
  $$("#browseRes input").forEach((c) => c.onchange = tray);
  $$("[data-open]").forEach((a) => a.onclick = (e) => { e.preventDefault(); openAccount(+a.dataset.open); });
  $("#prev").onclick = () => { D.page--; browse(); };
  $("#next").onclick = () => { D.page++; browse(); };
  tray();
}

function selected() {
  const D = state.discover;
  if (D.mode === "radar") return $$("#hits input:checked").map((c) => D.hits[+c.dataset.i]);
  return $$("#browseRes input:checked").map((c) => D.browse.companies[+c.dataset.b]);
}

function tray() {
  $(".tray")?.remove();
  const picks = selected();
  if (!picks.length || state.view !== "discover") return;
  const t = document.createElement("div");
  t.className = "tray";
  t.innerHTML = `<span>${picks.length} selected</span><button class="btn primary">Research ${picks.length === 1 ? "it" : `all ${picks.length}`}</button>`;
  $("button", t).onclick = async () => {
    try {
      const r = await api("/api/accounts/bulk", { method: "POST", body: JSON.stringify({ companies: picks.map((p) => ({ name: p.name, domain: p.domain || null })) }) });
      toast(`Researching ${r.queued} ${r.queued === 1 ? "company" : "companies"}. They'll appear on the left as they finish.`);
      $$("#view input:checked").forEach((c) => { c.checked = false; c.disabled = true; });
      t.remove(); watchList();
    } catch (e) { toast(e.message); }
  };
  document.body.appendChild(t);
}

function watchList() {
  clearInterval(window.listPoll);
  window.listPoll = setInterval(async () => {
    const list = await loadAccounts();
    if (!list.some((a) => a.status === "queued" || a.status === "running")) clearInterval(window.listPoll);
  }, 4000);
}

/* ------------------------------------------------------------------ forms & settings */

$$(".nav-btn").forEach((b) => b.onclick = () => (b.dataset.view === "discover" ? renderDiscover() : b.dataset.view === "alerts" ? renderAlerts() : renderHome()));

$("#addForm").onsubmit = async (e) => {
  e.preventDefault();
  const name = $("#name").value.trim();
  if (!name) return;
  try {
    const r = await api("/api/accounts", { method: "POST", body: JSON.stringify({ name, domain: $("#domain").value }) });
    $("#name").value = ""; $("#domain").value = "";
    await openAccount(r.company_id);
  } catch (err) { toast(err.message); }
};

$("#bulkForm").onsubmit = async (e) => {
  e.preventDefault();
  const companies = $("#bulk").value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
    const [name, domain] = l.split(",").map((x) => x.trim());
    return { name, domain: domain || null };
  });
  if (!companies.length) return;
  try {
    const r = await api("/api/accounts/bulk", { method: "POST", body: JSON.stringify({ companies }) });
    $("#bulk").value = "";
    toast(`Researching ${r.queued} companies, one after another`);
    watchList();
  } catch (err) { toast(err.message); }
};

$("#settingsBtn").onclick = async () => {
  const p = await api("/api/profile");
  $("#profJson").value = JSON.stringify(p.profile, null, 2);
  $("#profMsg").textContent = "Initiative categories you can use: " + Object.keys(p.categories).join(", ");
  $("#settings").showModal();
};
$("#saveProfile").onclick = async () => {
  try {
    await api("/api/profile", { method: "PUT", body: JSON.stringify(JSON.parse($("#profJson").value)) });
    $("#profMsg").textContent = "Profile saved. Research an account again to re-score it.";
    loadHealth();
  } catch (e) { $("#profMsg").textContent = "Couldn't save: " + e.message; }
};
$("#genProfile").onclick = async () => {
  $("#profMsg").textContent = "Drafting…";
  try {
    const p = await api("/api/profile/generate", { method: "POST", body: JSON.stringify({ company: $("#profCompany").value, description: $("#profDesc").value }) });
    $("#profJson").value = JSON.stringify(p, null, 2);
    $("#profMsg").textContent = "Drafted and saved. Edit it here if anything is off.";
    loadHealth();
  } catch (e) { $("#profMsg").textContent = "Couldn't draft: " + e.message; }
};

(async () => {
  await loadHealth();
  updateAlertBadge();
  const list = await loadAccounts();
  renderHome();
  if (list.some((a) => a.status === "queued" || a.status === "running")) watchList();
})();
