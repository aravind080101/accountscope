/**
 * AccountScope on Cloudflare.
 *
 * - Every request goes to one Python container (the FastAPI app + React UI).
 * - The container has no persistent disk, so all data lives in D1. The container talks to D1 by
 *   calling http://d1.internal/query; the outbound handler below runs inside the Workers runtime
 *   with the D1 binding, so no database credentials ever enter the container.
 * - A Cron Trigger re-researches watched accounts.
 */
import { Container, ContainerProxy, getContainer } from "@cloudflare/containers";
import type { DurableObject } from "cloudflare:workers";
import { runStatements, type Statement } from "./d1";

export { ContainerProxy };

interface Env {
  APP: DurableObjectNamespace<AppContainer>;
  DB: D1Database;
  INTERNAL_TOKEN?: string;
  [key: string]: unknown;
}

// Passed from Worker vars/secrets into the container's environment.
const PASS_THROUGH = [
  "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TAVILY_API_KEY", "APOLLO_API_KEY", "BUILTWITH_API_KEY",
  "ADMIN_EMAIL", "ADMIN_PASSWORD", "INTERNAL_TOKEN",
  "LLM_PROVIDER", "OPENAI_MODEL", "LLM_MODEL", "CONNECTION_NOTE_MAX", "WATCH_INTERVAL_DAYS",
  "SOURCE_CACHE_HOURS", "PEOPLE_CACHE_DAYS", "LOOKBACK_DAYS", "RESULTS_PER_QUERY",
];

export class AppContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "2h"; // research runs keep it awake (see renew below); idle containers stop to save cost

  constructor(ctx: DurableObject["ctx"], env: Env) {
    super(ctx, env);
    const vars: Record<string, string> = {
      RUNNING_IN_CLOUD: "1",
      D1_PROXY_URL: "http://d1.internal",
      WATCH_SCHEDULER: "off",
    };
    for (const k of PASS_THROUGH) {
      const v = env[k];
      if (typeof v === "string" && v) vars[k] = v;
    }
    this.envVars = vars;
  }
}

let lastRenew = 0;

AppContainer.outboundByHost = {
  "d1.internal": async (request: Request, env: unknown, ctx: { containerId: string }) => {
    const e = env as Env;
    // A container that is busy with the database is working: keep it awake.
    if (Date.now() - lastRenew > 60_000) {
      lastRenew = Date.now();
      try {
        const stub = e.APP.get(e.APP.idFromString(ctx.containerId)) as unknown as { renewActivityTimeout: () => Promise<void> };
        Promise.resolve(stub.renewActivityTimeout()).catch(() => {});
      } catch { /* best effort */ }
    }
    try {
      const { statements } = (await request.json()) as { statements: Statement[] };
      return Response.json({ results: await runStatements(e.DB, statements) });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : String(err) });
    }
  },
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const req = new Request(request);
    req.headers.delete("x-accountscope-client-ip"); // only the free-hosting proxy may set this
    return getContainer(env.APP, "main").fetch(req);
  },

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    if (!env.INTERNAL_TOKEN) return;
    ctx.waitUntil(
      getContainer(env.APP, "main").fetch(
        new Request("http://container/api/internal/watch", {
          method: "POST",
          headers: { "x-internal-token": env.INTERNAL_TOKEN },
        }),
      ),
    );
  },
} satisfies ExportedHandler<Env>;
