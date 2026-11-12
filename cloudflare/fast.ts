/**
 * Fast read routes, answered by the Worker straight from D1.
 *
 * On the free setup every database query the Python app makes is a trip over the internet
 * (Render -> this Worker's /__d1/query -> D1). Pages like an account's Projects tab made ~30 of those
 * one after another. These handlers answer the busiest read-only screens here instead, next to D1, in a
 * couple of batched round trips. They return exactly what the Python routes in backend/app.py return.
 *
 * Anything unexpected (an error, a route variant not handled here) returns null and the request goes on
 * to the Python app as before, so a bug here can make a page slower, never wrong.
 */

type Row = Record<string, any>;

// backend/taxonomy.py CATEGORIES[...]["label"]
const CATEGORY_LABELS: Record<string, string> = {
  qa_testing: "QA / testing",
  app_launch: "New app / product launch",
  cloud_migration: "Cloud migration",
  app_modernization: "Application / core modernisation",
  data_ai: "Data & AI / GenAI",
  cybersecurity: "Cybersecurity",
  erp_crm: "ERP / CRM rollout",
  devops_platform: "DevOps / platform engineering",
  compliance: "Regulatory / compliance programme",
  gcc_expansion: "GCC / new centre / expansion",
  other: "Other",
};
const label = (cat: string | null) => CATEGORY_LABELS[cat ?? ""] ?? CATEGORY_LABELS.other;

const COOKIE = "as_session";

export interface FastEnv {
  DB: D1Database;
  WATCH_INTERVAL_DAYS?: string;
}

type User = { id: number; workspace_id: number; must_change_password: number };

const json = (data: unknown, status = 200) => Response.json(data, { status });
const parseList = (v: unknown) => {
  try {
    return JSON.parse((v as string) || "[]");
  } catch {
    return [];
  }
};

function cookie(request: Request, name: string): string | null {
  for (const part of (request.headers.get("cookie") || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim().replace(/^"|"$/g, "");
  }
  return null;
}

async function sha256Hex(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Same check as backend/auth.py session_user. */
async function sessionUser(request: Request, db: D1Database): Promise<User | null> {
  const token = cookie(request, COOKIE);
  if (!token) return null;
  const r = await db
    .prepare(
      `SELECT u.id, u.must_change_password, u.workspace_id home_workspace, a.workspace_id, a.expires_at
       FROM auth_session a JOIN app_user u ON u.id=a.user_id WHERE a.token_hash=? AND u.active=1`,
    )
    .bind(await sha256Hex(token))
    .first<Row>();
  if (!r || !(Date.parse(r.expires_at) > Date.now())) return null;
  return { id: r.id, workspace_id: r.workspace_id || r.home_workspace, must_change_password: r.must_change_password };
}

/** Results of one D1 batch (a single round trip), as plain row lists. */
async function batch(db: D1Database, stmts: D1PreparedStatement[]): Promise<Row[][]> {
  if (!stmts.length) return [];
  return (await db.batch<Row>(stmts)).map((r) => r.results ?? []);
}

function groupBy(rows: Row[], key: string): Map<number, Row[]> {
  const m = new Map<number, Row[]>();
  for (const r of rows) {
    const k = r[key];
    delete r[key];
    if (!m.has(k)) m.set(k, []);
    m.get(k)!.push(r);
  }
  return m;
}

// ------------------------------------------------------------------ routes

// Keep in step with backend/db.py STALE_MINUTES / INTERRUPTED. A live research run touches run.updated_at every
// minute; one silent for longer died with its server (memory limit, redeploy), so stop showing "Researching".
const STALE_MINUTES = 5;
const INTERRUPTED = "Research stopped because the app server restarted while it was running " +
  "(an update or the free server's memory limit). Click Research again.";

async function failStaleRuns(db: D1Database, wid: number): Promise<void> {
  try {
    await db.prepare(
      `UPDATE run SET status='failed', error=?, finished_at=CURRENT_TIMESTAMP
       WHERE status IN ('queued','running')
         AND COALESCE(updated_at, started_at) < datetime('now', '-${STALE_MINUTES} minutes')
         AND company_id IN (SELECT id FROM company WHERE workspace_id=?)`,
    ).bind(INTERRUPTED, wid).run();
  } catch {
    // never break a page over this (e.g. the updated_at column not added yet)
  }
}

/** GET /api/accounts */
async function listAccounts(db: D1Database, wid: number) {
  await failStaleRuns(db, wid);
  const [companies, best] = await batch(db, [
    db.prepare(
      `SELECT c.id, c.name, c.domain, c.industry, c.hq_country, c.watch, c.last_researched_at,
       (SELECT COUNT(*) FROM initiative i WHERE i.company_id=c.id AND COALESCE(i.feedback,'')!='dismissed') AS initiatives,
       (SELECT COUNT(*) FROM project p WHERE p.company_id=c.id AND COALESCE(p.feedback,'')!='dismissed') AS projects,
       (SELECT COUNT(*) FROM alert a WHERE a.company_id=c.id AND a.read=0) AS unread,
       (SELECT COUNT(*) FROM document d WHERE d.company_id=c.id) AS documents,
       (SELECT status FROM run r WHERE r.company_id=c.id ORDER BY r.id DESC LIMIT 1) AS status
       FROM company c WHERE c.workspace_id=? ORDER BY c.id DESC`,
    ).bind(wid),
    // each account's best initiative and its best contact (backend/app.py runs two queries per account for this)
    db.prepare(
      `WITH best AS (
         SELECT i.company_id, i.id, i.name, i.fit_score, i.stage, i.basis,
                ROW_NUMBER() OVER (PARTITION BY i.company_id ORDER BY i.fit_score DESC, i.confidence DESC) rn
         FROM initiative i JOIN company c ON c.id=i.company_id
         WHERE c.workspace_id=? AND COALESCE(i.feedback,'')!='dismissed')
       SELECT b.company_id, b.id, b.name, b.fit_score, b.stage, b.basis,
              o.full_name o_full_name, o.title o_title, o.role o_role
       FROM best b LEFT JOIN (
         SELECT ic.initiative_id, p.full_name, p.title, ic.role,
                ROW_NUMBER() OVER (PARTITION BY ic.initiative_id ORDER BY ic.role='Owner' DESC, ic.score DESC) rn
         FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
         WHERE COALESCE(ic.feedback,'')!='rejected') o ON o.initiative_id=b.id AND o.rn=1
       WHERE b.rn=1`,
    ).bind(wid),
  ]);
  const byCompany = new Map(best.map((b) => [b.company_id, b]));
  for (const c of companies) {
    const b = byCompany.get(c.id);
    c.best = b ? { id: b.id, name: b.name, fit_score: b.fit_score, stage: b.stage, basis: b.basis } : null;
    c.owner = b && b.o_full_name !== null && b.o_full_name !== undefined
      ? { full_name: b.o_full_name, title: b.o_title, role: b.o_role } : null;
  }
  return companies;
}

/** GET /api/accounts/{cid} */
async function accountDetail(db: D1Database, wid: number, cid: number, env: FastEnv) {
  await failStaleRuns(db, wid);
  const [companyRows, inits, dismissed, runRows, docs, unread, mix, projs] = await batch(db, [
    db.prepare("SELECT * FROM company WHERE id=? AND workspace_id=?").bind(cid, wid),
    db.prepare(
      `SELECT * FROM initiative WHERE company_id=? AND COALESCE(feedback,'')!='dismissed'
       ORDER BY feedback='confirmed' DESC, fit_score DESC, confidence DESC`,
    ).bind(cid),
    db.prepare("SELECT COUNT(*) n FROM initiative WHERE company_id=? AND feedback='dismissed'").bind(cid),
    db.prepare("SELECT * FROM run WHERE company_id=? ORDER BY id DESC LIMIT 1").bind(cid),
    db.prepare("SELECT COUNT(*) n FROM document WHERE company_id=?").bind(cid),
    db.prepare("SELECT COUNT(*) n FROM alert WHERE company_id=? AND read=0").bind(cid),
    db.prepare("SELECT source_type, COUNT(*) n FROM document WHERE company_id=? GROUP BY source_type").bind(cid),
    db.prepare(
      `SELECT * FROM project WHERE company_id=? AND COALESCE(feedback,'')!='dismissed'
       ORDER BY feedback='confirmed' DESC, fit_score DESC, COALESCE(last_seen, first_seen) DESC`,
    ).bind(cid),
  ]);
  const company = companyRows[0];
  if (!company) return json({ detail: "Account not found" }, 404);

  const initIds = JSON.stringify(inits.map((i) => i.id));
  const projIds = JSON.stringify(projs.map((p) => p.id));
  const counterparties = JSON.stringify([...new Set(projs.filter((p) => p.counterparty != null).map((p) => String(p.counterparty)))]);
  const [ev, contacts, pev, pcontacts, accts] = await batch(db, [
    db.prepare(
      `SELECT e.initiative_id _k, d.source_type, d.url, d.title, d.published_at, e.quote FROM initiative_evidence e
       JOIN document d ON d.id=e.document_id WHERE e.initiative_id IN (SELECT value FROM json_each(?))
       ORDER BY d.published_at DESC`,
    ).bind(initIds),
    db.prepare(
      `SELECT ic.initiative_id _k, ic.id, ic.role, ic.score, ic.rationale, ic.opener, ic.feedback, p.id person_id, p.full_name, p.title, p.email,
       (SELECT 1 FROM buyer_brief b WHERE b.person_id=p.id) has_brief,
       p.phone, p.linkedin_url, ic.source FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
       WHERE ic.initiative_id IN (SELECT value FROM json_each(?)) ORDER BY ic.feedback='confirmed' DESC, ic.score DESC`,
    ).bind(initIds),
    db.prepare(
      `SELECT e.project_id _k, d.source_type, d.url, d.title, d.published_at, e.quote FROM project_evidence e
       JOIN document d ON d.id=e.document_id WHERE e.project_id IN (SELECT value FROM json_each(?))
       ORDER BY d.published_at DESC`,
    ).bind(projIds),
    db.prepare(
      `SELECT pc.project_id _k, pc.id, pc.role, pc.score, pc.rationale, pc.feedback, pc.source, p.id person_id, p.full_name, p.title,
       p.email, p.phone, p.linkedin_url, (SELECT 1 FROM buyer_brief b WHERE b.person_id=p.id) has_brief
       FROM project_contact pc JOIN person p ON p.id=pc.person_id
       WHERE pc.project_id IN (SELECT value FROM json_each(?)) AND COALESCE(pc.feedback,'')!='rejected'
       ORDER BY pc.feedback='confirmed' DESC, pc.score DESC`,
    ).bind(projIds),
    // backend/projects.py: the account (in this workspace) whose name matches the counterparty, ignoring case
    db.prepare(
      `SELECT j.value cp, (SELECT c.id FROM company c WHERE c.workspace_id=? AND LOWER(c.name)=LOWER(j.value)
       ORDER BY c.id LIMIT 1) id FROM json_each(?) j`,
    ).bind(company.workspace_id, counterparties),
  ]);

  const evBy = groupBy(ev, "_k"), ctBy = groupBy(contacts, "_k");
  for (const i of inits) {
    i.tech = parseList(i.tech);
    i.category_label = label(i.category);
    i.evidence = evBy.get(i.id) ?? [];
    i.contacts = ctBy.get(i.id) ?? [];
  }
  const pevBy = groupBy(pev, "_k"), pctBy = groupBy(pcontacts, "_k");
  const acctBy = new Map(accts.map((a) => [a.cp, a.id]));
  for (const p of projs) {
    for (const k of ["tech", "counterparty_people", "owner_titles"]) p[k] = parseList(p[k]);
    p.evidence = pevBy.get(p.id) ?? [];
    p.contacts = pctBy.get(p.id) ?? [];
    p.counterparty_account_id = p.counterparty == null ? null : acctBy.get(String(p.counterparty)) ?? null;
  }
  const run = runRows[0] ? { ...runRows[0], log: parseList(runRows[0].log) } : null;
  const days = parseFloat(env.WATCH_INTERVAL_DAYS || "7");
  return json({
    company, initiatives: inits, projects: projs, run, documents: docs[0].n, dismissed: dismissed[0].n,
    unread_alerts: unread[0].n, source_mix: Object.fromEntries(mix.map((r) => [r.source_type, r.n])),
    watch_every_days: days,
  });
}

/** GET /api/runs/{rid} */
async function runStatus(db: D1Database, wid: number, rid: number) {
  await failStaleRuns(db, wid);
  const r = await db
    .prepare("SELECT r.* FROM run r JOIN company c ON c.id=r.company_id WHERE r.id=? AND c.workspace_id=?")
    .bind(rid, wid)
    .first<Row>();
  if (!r) return json({ detail: "Run not found" }, 404);
  r.log = parseList(r.log);
  return json(r);
}

/** GET /api/summary */
async function summary(db: D1Database, wid: number) {
  const [a, w, pr, ow, un, top, recent] = await batch(db, [
    db.prepare("SELECT COUNT(*) n FROM company WHERE workspace_id=?").bind(wid),
    db.prepare("SELECT COUNT(*) n FROM company WHERE watch=1 AND workspace_id=?").bind(wid),
    db.prepare(`SELECT COUNT(*) n FROM initiative i JOIN company c ON c.id=i.company_id
                WHERE COALESCE(i.feedback,'')!='dismissed' AND c.workspace_id=?`).bind(wid),
    db.prepare(`SELECT COUNT(DISTINCT ic.person_id) n FROM initiative_contact ic JOIN initiative i ON i.id=ic.initiative_id
                JOIN company c ON c.id=i.company_id WHERE ic.role='Owner'
                AND COALESCE(ic.feedback,'')!='rejected' AND c.workspace_id=?`).bind(wid),
    db.prepare("SELECT COUNT(*) n FROM alert a JOIN company c ON c.id=a.company_id WHERE a.read=0 AND c.workspace_id=?").bind(wid),
    db.prepare(
      `SELECT i.id, i.name, i.stage, i.fit_score, i.basis, i.category, c.id company_id, c.name company,
       (SELECT p.full_name FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
         WHERE ic.initiative_id=i.id AND COALESCE(ic.feedback,'')!='rejected' ORDER BY ic.score DESC LIMIT 1) top_contact,
       (SELECT p.title FROM initiative_contact ic JOIN person p ON p.id=ic.person_id
         WHERE ic.initiative_id=i.id AND COALESCE(ic.feedback,'')!='rejected' ORDER BY ic.score DESC LIMIT 1) top_title
       FROM initiative i JOIN company c ON c.id=i.company_id WHERE COALESCE(i.feedback,'')!='dismissed'
       AND c.workspace_id=? ORDER BY i.fit_score DESC, i.confidence DESC LIMIT 8`,
    ).bind(wid),
    db.prepare(
      `SELECT a.id, a.kind, a.title, a.created_at, a.read, c.id company_id, c.name company FROM alert a
       JOIN company c ON c.id=a.company_id WHERE c.workspace_id=? ORDER BY a.id DESC LIMIT 6`,
    ).bind(wid),
  ]);
  for (const t of top) t.category_label = label(t.category);
  return json({
    totals: { accounts: a[0].n, watched: w[0].n, projects: pr[0].n, owners: ow[0].n, unread: un[0].n },
    top_projects: top,
    recent_alerts: recent,
  });
}

/** GET /api/alerts[?company_id=&unread=] */
async function listAlerts(db: D1Database, wid: number, url: URL) {
  let q = "SELECT a.*, c.name company FROM alert a JOIN company c ON c.id=a.company_id WHERE c.workspace_id=?";
  const args: unknown[] = [wid];
  const cid = url.searchParams.get("company_id");
  if (cid !== null) {
    if (!/^-?\d+$/.test(cid)) return null; // let FastAPI produce its validation error
    if (Number(cid)) {
      q += " AND a.company_id=?";
      args.push(Number(cid));
    }
  }
  const un = url.searchParams.get("unread");
  if (un !== null) {
    const v = un.toLowerCase();
    if (["1", "true", "yes", "on", "t", "y"].includes(v)) q += " AND a.read=0";
    else if (!["0", "false", "no", "off", "f", "n"].includes(v)) return null;
  }
  const [rows, n] = await batch(db, [
    db.prepare(q + " ORDER BY a.id DESC LIMIT 300").bind(...args),
    db.prepare("SELECT COUNT(*) n FROM alert a JOIN company c ON c.id=a.company_id WHERE a.read=0 AND c.workspace_id=?").bind(wid),
  ]);
  return json({ alerts: rows, unread: n[0].n });
}

// ------------------------------------------------------------------ entry

const ROUTES: [RegExp, (db: D1Database, wid: number, m: RegExpMatchArray, url: URL, env: FastEnv) => Promise<Response | null>][] = [
  [/^\/api\/accounts$/, async (db, wid) => json(await listAccounts(db, wid))],
  [/^\/api\/accounts\/(\d+)$/, (db, wid, m, _u, env) => accountDetail(db, wid, Number(m[1]), env)],
  [/^\/api\/runs\/(\d+)$/, (db, wid, m) => runStatus(db, wid, Number(m[1]))],
  [/^\/api\/summary$/, (db, wid) => summary(db, wid)],
  [/^\/api\/alerts$/, (db, wid, _m, url) => listAlerts(db, wid, url)],
];

/** A Response if this Worker can answer the request itself, else null (forward it to the Python app). */
export async function fastRoute(request: Request, env: FastEnv): Promise<Response | null> {
  if (request.method !== "GET" || !env.DB) return null;
  const url = new URL(request.url);
  for (const [re, handler] of ROUTES) {
    const m = url.pathname.match(re);
    if (!m) continue;
    try {
      const user = await sessionUser(request, env.DB);
      if (!user) return json({ detail: "Not signed in" }, 401);
      if (user.must_change_password) return json({ detail: "Change your temporary password first" }, 403);
      const resp = await handler(env.DB, user.workspace_id, m, url, env);
      if (resp) resp.headers.set("x-served-by", "worker");
      return resp;
    } catch (err) {
      console.error("fast route failed, forwarding to the app", url.pathname, err);
      return null;
    }
  }
  return null;
}
