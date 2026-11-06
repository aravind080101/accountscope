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
