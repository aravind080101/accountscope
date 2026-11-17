/** All API calls go through here: they carry the app header (blocks cross-site form posts) and
 *  signal the app to show the sign-in screen when the session has ended. */
export const APP_HEADER = { "X-Requested-With": "accountscope" };

export async function api<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const isForm = opts.body instanceof FormData;
  const res = await fetch(path, {
    credentials: "same-origin",
    ...opts,
    headers: { ...(isForm ? {} : { "Content-Type": "application/json" }), ...APP_HEADER, ...(opts.headers || {}) },
  });
  const isJson = res.headers.get("content-type")?.includes("json");
  const body = isJson ? await res.json() : await res.text();
  if (res.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event("as:signedout"));
  if (!res.ok) throw new Error((body && (body as any).detail) || String(body) || res.statusText);
  return body as T;
}
export const post = <T = any>(path: string, data?: unknown) => api<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });


/** Say exactly what Get email found: email, LinkedIn (and where from), and why anything is missing. */
export function reportEnrich(r: any) {
  // imported lazily to keep this file free of UI deps at module load
  import("sonner").then(({ toast }) => {
    const parts = [r?.found?.includes("email") && "email", r?.found?.includes("linkedin_url") && `LinkedIn${r?.linkedin_source === "web search" ? " (from a web search)" : ""}`].filter(Boolean);
    if (parts.length) toast.success(`Found ${parts.join(" and ")}`);
    else toast.info("Nothing new found; showing what's already saved");
    if (r?.missing?.includes("email")) toast.info(r?.apollo_error ? `No email: Apollo said ${r.apollo_error}` : "Apollo has no email for this person");
    if (r?.missing?.includes("linkedin_url")) toast.info("No LinkedIn profile found. Paste it on the person if you have it.");
  });
}
