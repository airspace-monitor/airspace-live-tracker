/** Shapes from docs/05-api-contract.md. Units are SI; timestamps are ISO-8601 UTC. */

export interface Stats {
  aircraft_now: number
  snapshot_time: string | null
  collectors_online: number
  rows_today: number
  dq_status: string | null
}

export type EventSeverity = 'info' | 'warn' | 'alert'

export interface EventRow {
  event_id: number
  ts: string
  kind: string
  severity: EventSeverity
  title: string
  icao24: string | null
  airport_icao: string | null
  lon: number | null
  lat: number | null
}

export interface EventsPage {
  events: EventRow[]
  next_cursor: { before_ts: string; before_id: number } | null
}
