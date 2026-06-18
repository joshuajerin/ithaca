import { useCallback, useEffect, useState } from "react";

// Minimal data-fetch hook (plain fetch, no react-query dependency). Re-runs when deps change
// and aborts in-flight requests on unmount/refetch.
export function useAsync<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
): { data: T | null; loading: boolean; error: string | null; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    fn(ctrl.signal)
      .then((d) => {
        if (!ctrl.signal.aborted) {
          setData(d);
          setLoading(false);
        }
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, loading, error, reload };
}
