import { useCallback, useEffect, useRef, useState } from "react";

import { apiGet } from "../lib/api";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Concurrent identical GETs are coalesced: while ``/analytics`` (say) is still
 * in flight, a second hook requesting the same path awaits the same network
 * call instead of firing a duplicate request (the dashboard fetches ``/health``
 * that AppShell also fetches, so without this they would make two round-trips).
 */
const inflight = new Map<string, Promise<unknown>>();

function fetchOnce<T>(path: string): Promise<T> {
  const key = path;
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;
  const promise = apiGet<T>(path).then(
    (result) => {
      inflight.delete(key);
      return result;
    },
    (error: unknown) => {
      inflight.delete(key);
      throw error;
    },
  );
  inflight.set(key, promise);
  return promise;
}

/**
 * Small data-fetching hook: loading / error / data / reload.
 * On error it keeps the last successfully loaded payload (if any) so a
 * transient network failure does not blank the whole viewport — the caller
 * renders the error state alongside whatever data it still has.
 */
export function useApi<T>(path: string): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [attempt, setAttempt] = useState(0);
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;
    setLoading(true);
    setError(null);

    fetchOnce<T>(path)
      .then((result) => {
        if (!activeRef.current) return;
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!activeRef.current) return;
        setError(err instanceof Error ? err.message : "Unexpected error");
      })
      .finally(() => {
        if (activeRef.current) setLoading(false);
      });

    return () => {
      activeRef.current = false;
    };
  }, [path, attempt]);

  const reload = useCallback(() => {
    activeRef.current = true;
    setAttempt((value) => value + 1);
  }, []);

  return { data, error, loading, reload };
}
