/**
 * AccountScope on Cloudflare's FREE plan.
 *
 * Containers need Workers Paid, so on the free plan the Python app runs on a free Render web service
 * and this Worker sits in front of it:
 *
 * - Every visit to https://accountscope.<you>.workers.dev is forwarded to the app (APP_ORIGIN), stamped
 *   with x-proxy-token; the app refuses requests without it, so its own onrender.com address is useless.
 * - /__d1/query is how the app reads and writes the D1 database. It is public, so it requires the
 *   shared INTERNAL_TOKEN.
 * - The Cron Trigger starts due watch runs (and wakes the app, which sleeps after 15 minutes idle).
 */
import { DurableObject } from "cloudflare:workers";
import { runStatements, type Statement } from "./d1";

interface Env {
  DB: D1Database;
  APP_ORIGIN?: string; // e.g. https://accountscope.onrender.com
  INTERNAL_TOKEN?: string;
}

// Left over from the first (container) deploy attempt; kept so that deploy needs no migration.
export class AppContainer extends DurableObject {}

const HOP = ["host", "connection", "keep-alive", "transfer-encoding", "upgrade", "x-proxy-token",
  "x-accountscope-client-ip", "cf-connecting-ip", "cf-ipcountry", "cf-ray", "cf-visitor", "x-forwarded-proto",
  "x-real-ip"];

function sameSecret(a: string, b: string): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function origin(env: Env): string {
  return (env.APP_ORIGIN || "").replace(/\/+$/, "");
}

function toApp(env: Env, path: string, init: RequestInit & { headers?: Headers } = {}): Promise<Response> {
  const headers = init.headers ?? new Headers();
  if (env.INTERNAL_TOKEN) headers.set("x-proxy-token", env.INTERNAL_TOKEN);
  return fetch(origin(env) + path, { ...init, headers, redirect: "manual" });
}

const SETUP_PAGE = (msg: string) => new Response(
  `<!doctype html><meta charset=utf-8><title>AccountScope</title>
<body style="font:15px system-ui;max-width:560px;margin:15vh auto;padding:0 20px;color:#222">
<h2>AccountScope is starting</h2><p>${msg}</p><p>This page refreshes by itself.</p>
<script>setTimeout(()=>location.reload(),15000)</script>`,
  { status: 503, headers: { "content-type": "text/html; charset=utf-8", "retry-after": "15" } },
);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/__d1/query") {
      if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
      if (!sameSecret(request.headers.get("x-internal-token") || "", env.INTERNAL_TOKEN || "")) {
        return new Response("Forbidden", { status: 403 });
      }
      try {
        const { statements } = (await request.json()) as { statements: Statement[] };
        return Response.json({ results: await runStatements(env.DB, statements) });
      } catch (err) {
        return Response.json({ error: err instanceof Error ? err.message : String(err) });
      }
    }

    if (!origin(env)) return SETUP_PAGE("The app address (APP_ORIGIN) isn't set yet. Run scripts/deploy_free.py.");

    const headers = new Headers();
    for (const [k, v] of request.headers) if (!HOP.includes(k.toLowerCase())) headers.set(k, v);
    headers.set("x-accountscope-client-ip", request.headers.get("cf-connecting-ip") || "");
    headers.set("x-forwarded-proto", "https");
    headers.set("x-forwarded-host", url.host);

    let resp: Response;
    try {
      resp = await toApp(env, url.pathname + url.search, {
        method: request.method,
        headers,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      });
    } catch {
      return SETUP_PAGE("The app server is waking up. The free server sleeps after 15 minutes without visitors; this takes about a minute.");
    }

    // A sleeping or restarting app answers with Render's own page: show ours instead.
    const type = resp.headers.get("content-type") || "";
    if (resp.status >= 500 && type.includes("text/html")) {
      return SETUP_PAGE("The app server is waking up. The free server sleeps after 15 minutes without visitors; this takes about a minute.");
    }

    // Redirects from the app point at the Space's address: rewrite them to ours.
    const out = new Response(resp.body, resp);
    const loc = out.headers.get("location");
    if (loc && loc.startsWith(origin(env))) out.headers.set("location", loc.slice(origin(env).length) || "/");
    return out;
  },

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    if (!origin(env) || !env.INTERNAL_TOKEN) return;
    const headers = new Headers({ "x-internal-token": env.INTERNAL_TOKEN });
    ctx.waitUntil(toApp(env, "/api/internal/watch", { method: "POST", headers }).catch(() => undefined));
  },
} satisfies ExportedHandler<Env>;
