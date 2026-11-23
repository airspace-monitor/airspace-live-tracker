import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { API_BASE } from '../api/client'

/**
 * Keeps the REST queries fresh from the SSE stream (docs/08-frontend.md#data-flow).
 * EventSource reconnects on its own; every open or snapshot_ready refreshes `/stats`.
 * The map consumes the same stream in M2.5; this hook only wires the header.
 */
export function useLiveStream(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/live/stream`)
    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: ['stats'] })
    }

    source.addEventListener('snapshot_ready', refresh)
    source.addEventListener('open', refresh)

    return () => {
      source.removeEventListener('snapshot_ready', refresh)
      source.removeEventListener('open', refresh)
      source.close()
    }
  }, [queryClient])
}
