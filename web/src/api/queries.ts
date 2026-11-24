import { useQuery } from '@tanstack/react-query'
import { EVENTS_LIMIT, STATS_REFETCH_MS } from '../lib/config'
import { getJson } from './client'
import type { AircraftDetail, EventsPage, Snapshot, Stats } from './types'

export function useLiveSnapshot() {
  return useQuery({
    queryKey: ['snapshot'],
    queryFn: ({ signal }) => getJson<Snapshot>('/live/snapshot', signal),
    refetchInterval: 90_000,
    staleTime: 60_000,
  })
}

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

export function useAircraft(icao24: string | null) {
  return useQuery({
    queryKey: ['aircraft', icao24],
    queryFn: ({ signal }) => getJson<AircraftDetail>(`/aircraft/${icao24}`, signal),
    enabled: icao24 !== null,
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}
