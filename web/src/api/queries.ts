import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { EVENTS_LIMIT, STATS_REFETCH_MS } from '../lib/config'
import { getJson } from './client'
import type { AircraftDetail, AircraftTrack, EventsPage, Snapshot, Stats } from './types'

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

/** Cursor-paged events for the infinite feed (docs/08-frontend.md#panels). */
export function useEventsInfinite(limit: number = EVENTS_LIMIT) {
  return useInfiniteQuery({
    queryKey: ['events', 'infinite', limit],
    queryFn: ({ pageParam, signal }) => {
      const cursor = pageParam as EventsPage['next_cursor']
      const query = cursor
        ? `limit=${limit}&before_ts=${encodeURIComponent(cursor.before_ts)}&before_id=${cursor.before_id}`
        : `limit=${limit}`
      return getJson<EventsPage>(`/events?${query}`, signal)
    },
    initialPageParam: null as EventsPage['next_cursor'],
    getNextPageParam: (lastPage) => lastPage.next_cursor,
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

export function useAircraftTrack(icao24: string | null, minutes = 60) {
  return useQuery({
    queryKey: ['aircraft-track', icao24, minutes],
    queryFn: ({ signal }) =>
      getJson<AircraftTrack>(`/aircraft/${icao24}/track?minutes=${minutes}`, signal),
    enabled: icao24 !== null,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}
