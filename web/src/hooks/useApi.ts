"use client";
import { useEffect, useState } from "react";
import { apiGet, staticGet } from "@/lib/api/client";

export interface ApiState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
}

/** Fetch a backend path (via /backend proxy) or, with `isStatic`, a file under public/. */
export function useApi<T>(path: string | null, isStatic = false): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ data: null, error: null, loading: !!path });
  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    (isStatic ? staticGet<T>(path) : apiGet<T>(path, { signal: ctrl.signal }))
      .then((data) => !ctrl.signal.aborted && setState({ data, error: null, loading: false }))
      .catch((error: Error) => !ctrl.signal.aborted && setState({ data: null, error, loading: false }));
    return () => ctrl.abort();
  }, [path, isStatic]);
  return state;
}
