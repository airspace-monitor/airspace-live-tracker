import type { Snapshot, SnapshotValue } from '../api/types'

export interface Aircraft {
  icao24: string
  callsign: string | null
  lon: number
  lat: number
  alt_m: number | null
  vel_ms: number | null
  track_deg: number | null
  vrate_ms: number | null
  on_ground: boolean | null
  pos_age_s: number | null
}

function asNumber(value: SnapshotValue | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asBoolean(value: SnapshotValue | undefined): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function asString(value: SnapshotValue | undefined): string | null {
  return typeof value === 'string' ? value : null
}

/**
 * Turn the column-oriented snapshot from `/live/snapshot` into typed rows.
 * States without a position are dropped; everything else keeps its nulls.
 */
export function parseAircraft(snapshot: Snapshot): Aircraft[] {
  const index = new Map(snapshot.fields.map((field, position) => [field, position]))
  const field = (row: SnapshotValue[], name: string): SnapshotValue | undefined =>
    row[index.get(name) ?? -1]

  const aircraft: Aircraft[] = []
  for (const row of snapshot.states) {
    const lon = asNumber(field(row, 'lon'))
    const lat = asNumber(field(row, 'lat'))
    const icao24 = asString(field(row, 'icao24'))
    if (lon === null || lat === null || !icao24) continue

    const callsign = asString(field(row, 'callsign'))?.trim() || null
    aircraft.push({
      icao24,
      callsign,
      lon,
      lat,
      alt_m: asNumber(field(row, 'alt_m')),
      vel_ms: asNumber(field(row, 'vel_ms')),
      track_deg: asNumber(field(row, 'track_deg')),
      vrate_ms: asNumber(field(row, 'vrate_ms')),
      on_ground: asBoolean(field(row, 'on_ground')),
      pos_age_s: asNumber(field(row, 'pos_age_s')),
    })
  }
  return aircraft
}
