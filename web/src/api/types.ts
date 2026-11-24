/** Shapes from docs/05-api-contract.md. Units are SI; timestamps are ISO-8601 UTC. */

export interface Stats {
  aircraft_now: number
  snapshot_time: string | null
  collectors_online: number
  rows_today: number
  dq_status: string | null
}

export type SnapshotValue = string | number | boolean | null

/** One live snapshot; `states` is column-oriented via `fields` (docs/05-api-contract.md). */
export interface Snapshot {
  snapshot_time: string
  next_expected_at: string
  fields: string[]
  states: SnapshotValue[][]
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

export interface AircraftState {
  time: string
  lon: number
  lat: number
  alt_m: number | null
  vel_ms: number | null
  track_deg: number | null
  vrate_ms: number | null
  pos_age_s: number | null
}

export interface AircraftFlight {
  flight_id: string
  first_seen: string | null
  dep_icao: string | null
  dep_source: string | null
}

export interface DestinationCandidate {
  icao: string
  p: number
}

export interface AircraftDestination {
  predicted_at: string
  method: string
  candidates: DestinationCandidate[]
}

export interface AircraftEta {
  airport_icao: string
  p10: string
  p50: string
  p90: string
  model_version: string
}

/** `GET /aircraft/{icao24}` (docs/05-api-contract.md). destination/eta are null until M4. */
export interface AircraftDetail {
  icao24: string
  callsign: string | null
  registration: string | null
  typecode: string | null
  operator: string | null
  airline: string | null
  last_state: AircraftState
  flight: AircraftFlight | null
  destination: AircraftDestination | null
  eta: AircraftEta | null
}
