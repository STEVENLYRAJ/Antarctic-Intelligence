/**
 * Centralised client for the AETHENTRA FastAPI backend.
 * The browser calls /backend/* which Next.js proxies to AETHENTRA_API_URL (see next.config.ts).
 */
export const API_BASE = "/backend";

export class ApiError extends Error {
  constructor(public status: number, public path: string, message: string) {
    super(message);
  }
}

export interface FetchOptions {
  retries?: number;
  signal?: AbortSignal;
}

export async function apiGet<T>(path: string, { retries = 2, signal }: FetchOptions = {}): Promise<T> {
  let last: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(`${API_BASE}${path}`, { signal, headers: { Accept: "application/json" } });
      if (!res.ok) {
        // 4xx responses are not retried: the resource does not exist or the request is wrong.
        const err = new ApiError(res.status, path, `${res.status} ${res.statusText}`);
        if (res.status < 500) throw err;
        last = err;
      } else {
        return (await res.json()) as T;
      }
    } catch (e) {
      if (signal?.aborted || (e instanceof ApiError && e.status < 500)) throw e;
      last = e;
    }
    if (attempt < retries) await new Promise((r) => setTimeout(r, 400 * 2 ** attempt));
  }
  throw last instanceof Error ? last : new Error(String(last));
}

/** Absolute URL for binary resources (PNG layers) served by the backend through the proxy. */
export const apiUrl = (path: string) => `${API_BASE}${path}`;

/** Static, pre-computed presentation data shipped with the frontend (public/data). */
export async function staticGet<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new ApiError(res.status, path, `${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}
