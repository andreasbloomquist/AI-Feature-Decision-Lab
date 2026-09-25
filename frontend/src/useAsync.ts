import { useEffect, useEffectEvent, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Run `load` whenever `key` changes and keep only the latest result.
 *
 * A response that arrives after a newer request has started is ignored, so switching runs or
 * filters quickly can never show data for the wrong selection. Pass `null` as the key to skip loading.
 */
export function useAsync<T>(key: string | null, load: () => Promise<T>): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: key !== null });
  const [nonce, setNonce] = useState(0);
  // `load` is rebuilt on every render; an effect event lets the effect call the latest one
  // while re-running only when `key` changes.
  const runLoad = useEffectEvent(load);

  useEffect(() => {
    if (key === null) return;
    let current = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    runLoad().then(
      (data) => current && setState({ data, error: null, loading: false }),
      (e: unknown) => current && setState({ data: null, error: e instanceof Error ? e.message : String(e), loading: false }),
    );
    return () => {
      current = false;
    };
  }, [key, nonce]);

  return { ...state, reload: () => setNonce((n) => n + 1) };
}
