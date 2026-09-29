import { useEffect, useEffectEvent, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Run `load` whenever `key` changes and keep only the latest result.
 *
 * A response that arrives after a newer request has started is ignored, and data loaded for an
 * earlier key is never returned for the current one, so switching runs, cases or filters can never
 * show (or act on) data for the wrong selection. Pass `null` as the key to skip loading.
 */
export function useAsync<T>(key: string | null, load: () => Promise<T>): AsyncState<T> & { reload: () => void } {
  // The settled result, tagged with the key and reload count it was loaded for. Loading state is
  // derived from those tags rather than set from the effect.
  const [settled, setSettled] = useState<{ key: string; nonce: number; data: T | null; error: string | null } | null>(null);
  const [nonce, setNonce] = useState(0);
  // `load` is rebuilt on every render; an effect event lets the effect call the latest one
  // while re-running only when `key` changes.
  const runLoad = useEffectEvent(load);

  useEffect(() => {
    if (key === null) return;
    let current = true;
    runLoad().then(
      (data) => current && setSettled({ key, nonce, data, error: null }),
      (e: unknown) => current && setSettled({ key, nonce, data: null, error: e instanceof Error ? e.message : String(e) }),
    );
    return () => {
      current = false;
    };
  }, [key, nonce]);

  const reload = () => setNonce((n) => n + 1);
  if (key === null) return { data: null, error: null, loading: false, reload };
  // Data loaded for a different key is never returned; a reload of the same key keeps showing the
  // previous data (without its error) until the new response arrives.
  if (settled?.key !== key) return { data: null, error: null, loading: true, reload };
  const loading = settled.nonce !== nonce;
  return { data: settled.data, error: loading ? null : settled.error, loading, reload };
}
