import type { Aircraft } from '../lib/aircraft'

/**
 * A live aircraft plus the state needed to animate it between snapshots.
 * `lon`/`lat` are the rendered position; the reported position lives in
 * `target*` and the previous rendered position in `from*`.
 */
export interface MotionAircraft extends Aircraft {
  targetLon: number
  targetLat: number
  fromLon: number
  fromLat: number
  easeStart: number | null
  baseLon: number
  baseLat: number
  baseTime: number
  missed: number
  fadeStart: number | null
  opacity: number
}

const EASE_MS = 1500
const FADE_MS = 1500
const MAX_EXTRAPOLATION_S = 120
const EARTH_RADIUS_M = 6_371_000

/** The docs/08 motion rules: no extrapolation for ground, slow, or stale states. */
export function canExtrapolate(aircraft: Aircraft): boolean {
  return (
    aircraft.pos_age_s !== null &&
    aircraft.pos_age_s <= 60 &&
    aircraft.on_ground !== true &&
    aircraft.vel_ms !== null &&
    aircraft.vel_ms >= 30 &&
    aircraft.track_deg !== null
  )
}

/** Flat-earth/great-circle step along `trackDeg` for `dtS` seconds. */
export function project(
  lon: number,
  lat: number,
  velMs: number | null,
  trackDeg: number | null,
  dtS: number,
): [number, number] {
  if (velMs === null || trackDeg === null || !Number.isFinite(dtS) || dtS <= 0) return [lon, lat]

  const distance = velMs * Math.min(dtS, MAX_EXTRAPOLATION_S)
  const bearing = (trackDeg * Math.PI) / 180
  const lat1 = (lat * Math.PI) / 180
  const lon1 = (lon * Math.PI) / 180
  const angular = distance / EARTH_RADIUS_M

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing),
  )
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
      Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
    )

  return [(((lon2 * 180) / Math.PI + 540) % 360) - 180, (lat2 * 180) / Math.PI]
}

/** Where the aircraft should be at `now`, from the reported position and age. */
export function targetPosition(
  aircraft: Aircraft,
  snapshotTimeMs: number | null,
  now: number,
): [number, number] {
  if (snapshotTimeMs === null || !Number.isFinite(snapshotTimeMs) || !canExtrapolate(aircraft))
    return [aircraft.lon, aircraft.lat]

  const t0 = snapshotTimeMs - (aircraft.pos_age_s ?? 0) * 1000
  const dtS = Math.min(Math.max((now - t0) / 1000, 0), MAX_EXTRAPOLATION_S)
  return project(aircraft.lon, aircraft.lat, aircraft.vel_ms, aircraft.track_deg, dtS)
}

/** Mutate one state forward. Returns false once a fading aircraft is fully gone. */
export function advanceOne(aircraft: MotionAircraft, now: number): boolean {
  if (aircraft.fadeStart !== null) {
    aircraft.opacity = Math.max(0, 1 - (now - aircraft.fadeStart) / FADE_MS)
    return aircraft.opacity > 0
  }

  if (aircraft.easeStart !== null) {
    const progress = Math.min(1, Math.max(0, (now - aircraft.easeStart) / EASE_MS))
    const eased = 1 - (1 - progress) ** 3
    aircraft.lon = aircraft.fromLon + (aircraft.targetLon - aircraft.fromLon) * eased
    aircraft.lat = aircraft.fromLat + (aircraft.targetLat - aircraft.fromLat) * eased

    if (progress >= 1) {
      aircraft.easeStart = null
      aircraft.baseLon = aircraft.targetLon
      aircraft.baseLat = aircraft.targetLat
      aircraft.baseTime = now
    }
    return true
  }

  const dtS = Math.min(Math.max((now - aircraft.baseTime) / 1000, 0), MAX_EXTRAPOLATION_S)
  const [lon, lat] = canExtrapolate(aircraft)
    ? project(aircraft.baseLon, aircraft.baseLat, aircraft.vel_ms, aircraft.track_deg, dtS)
    : [aircraft.baseLon, aircraft.baseLat]
  aircraft.lon = lon
  aircraft.lat = lat
  return true
}

export function advanceMotion(states: MotionAircraft[], now: number): MotionAircraft[] {
  let write = 0
  for (const state of states) {
    if (advanceOne(state, now)) states[write++] = state
  }
  states.length = write
  return states
}

/**
 * Merge a new snapshot into the animation state. Existing aircraft ease from
 * their current rendered position to the new dead-reckoned target; new ones
 * appear at the target; two missed snapshots start a 1.5 s fade-out.
 */
export function updateMotion(
  previous: MotionAircraft[],
  next: Aircraft[],
  snapshotTimeMs: number | null,
  now: number,
): MotionAircraft[] {
  const previousById = new Map(previous.map((state) => [state.icao24, state]))
  const seen = new Set<string>()
  const result: MotionAircraft[] = []

  for (const row of next) {
    seen.add(row.icao24)
    const [targetLon, targetLat] = targetPosition(row, snapshotTimeMs, now)
    const existing = previousById.get(row.icao24)

    if (existing) {
      advanceOne(existing, now)
      existing.fromLon = existing.lon
      existing.fromLat = existing.lat
      existing.targetLon = targetLon
      existing.targetLat = targetLat
      existing.easeStart = now
      existing.baseLon = targetLon
      existing.baseLat = targetLat
      existing.baseTime = now
      existing.callsign = row.callsign
      existing.alt_m = row.alt_m
      existing.vel_ms = row.vel_ms
      existing.track_deg = row.track_deg
      existing.vrate_ms = row.vrate_ms
      existing.on_ground = row.on_ground
      existing.pos_age_s = row.pos_age_s
      existing.missed = 0
      existing.fadeStart = null
      existing.opacity = 1
      result.push(existing)
    } else {
      result.push({
        ...row,
        lon: targetLon,
        lat: targetLat,
        targetLon,
        targetLat,
        fromLon: targetLon,
        fromLat: targetLat,
        easeStart: null,
        baseLon: targetLon,
        baseLat: targetLat,
        baseTime: now,
        missed: 0,
        fadeStart: null,
        opacity: 1,
      })
    }
  }

  for (const old of previous) {
    if (seen.has(old.icao24)) continue
    old.missed += 1
    if (old.missed >= 2 && old.fadeStart === null) old.fadeStart = now
    if (old.fadeStart !== null) {
      old.opacity = Math.max(0, 1 - (now - old.fadeStart) / FADE_MS)
      if (old.opacity <= 0) continue
    }
    result.push(old)
  }

  return result
}
