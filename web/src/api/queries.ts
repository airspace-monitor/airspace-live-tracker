import { useQuery } from '@tanstack/react-query'
import { EVENTS_LIMIT, STATS_REFETCH_MS } from '../lib/config'
import { getJson } from './client'
import type { EventsPage, Stats } from './types'

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: ({ signal }) => getJson<Stats>('/stats', signal),
    refetchInterval: STATS_REFETCH_MS,
    staleTime: STATS_REFETCH_MS / 2,
  })
}

export function useEvents(limit: number = EVENTS_LIMIT) {
  return useQuery({
    queryKey: ['events', limit],
    queryFn: ({ signal }) => getJson<EventsPage>(`/events?limit=${limit}`, signal),
    staleTime: 30_000,
  })
}
