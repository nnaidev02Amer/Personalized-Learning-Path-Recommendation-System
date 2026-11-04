import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Run an async loader and track { data, error, loading }.
 * Re-runs when `deps` change; stale responses from earlier runs are ignored.
 * Pass `null` as the loader to skip loading (e.g. while an id is unknown).
 */
export function useApi(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(loader) })
  const runId = useRef(0)

  const run = useCallback(async () => {
    if (!loader) {
      setState({ data: null, error: null, loading: false })
      return
    }
    const id = ++runId.current
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await loader()
      if (id === runId.current) setState({ data, error: null, loading: false })
    } catch (error) {
      if (id === runId.current) setState((s) => ({ ...s, error, loading: false }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
  }, [run])

  const setData = useCallback((updater) => {
    setState((s) => ({ ...s, data: typeof updater === 'function' ? updater(s.data) : updater }))
  }, [])

  return { ...state, reload: run, setData }
}

/** Debounce a changing value (used for search inputs). */
export function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}
