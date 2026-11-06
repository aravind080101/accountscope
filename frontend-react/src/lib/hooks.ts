import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export type Route = { page: "accounts" | "company" | "discover" | "alerts" | "outreach" | "team" | "workspaces"; id?: number; tab?: string };

function parse(): Route {
  const h = location.hash.replace(/^#\/?/, "");
  const [a, b, c] = h.split("/");
  if (a === "a" && b) return { page: "company", id: Number(b), tab: c || "initiatives" };
  if (a === "discover") return { page: "discover" };
  if (a === "alerts") return { page: "alerts" };
  if (a === "outreach") return { page: "outreach" };
  if (a === "team") return { page: "team" };
  if (a === "workspaces") return { page: "workspaces" };
  return { page: "accounts" };
}
export function useRoute(): Route {
  const [r, setR] = useState(parse());
  useEffect(() => { const f = () => setR(parse()); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return r;
}
export const go = (path: string) => { location.hash = path; };

/** Fetch JSON; refetch on deps change; optional polling while `pollWhile(data)` is true. */
export function useApi<T = any>(path: string | null, deps: unknown[] = [], pollWhile?: (d: T) => boolean, every = 2000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number>();
  const load = useCallback(async () => {
    if (!path) return;
    try { const d = await api<T>(path); setData(d); setError(null); return d; }
    catch (e: any) { setError(e.message); }
  }, [path]);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const d = await load();
      if (alive && d && pollWhile?.(d)) timer.current = window.setTimeout(tick, every);
    };
    setData(null); tick();
    return () => { alive = false; clearTimeout(timer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  return { data, error, reload: load, setData };
}
