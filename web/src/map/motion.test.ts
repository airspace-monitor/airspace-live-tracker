import { describe, expect, it } from 'vitest'
import type { Aircraft } from '../lib/aircraft'
import { advanceMotion, canExtrapolate, project, updateMotion } from './motion'

const AIRCRAFT: Aircraft = {
  icao24: 'abc123',
  callsign: 'AUA1',
  lon: 16.3,
  lat: 48.2,
  alt_m: 10000,
  vel_ms: 200,
  track_deg: 90,
  vrate_ms: 0,
  on_ground: false,
  pos_age_s: 0,
}

describe('project', () => {
  it('moves east along the track', () => {
    const [lon, lat] = project(0, 0, 100, 90, 10)
    expect(lon).toBeGreaterThan(0)
    expect(lat).toBeCloseTo(0, 6)
  })

  it('does not move without velocity or track', () => {
    expect(project(16, 48, null, 90, 10)).toEqual([16, 48])
    expect(project(16, 48, 100, null, 10)).toEqual([16, 48])
  })
})

describe('canExtrapolate', () => {
  it('rejects ground, slow, stale and missing-age aircraft', () => {
    expect(canExtrapolate({ ...AIRCRAFT, on_ground: true })).toBe(false)
    expect(canExtrapolate({ ...AIRCRAFT, vel_ms: 20 })).toBe(false)
    expect(canExtrapolate({ ...AIRCRAFT, pos_age_s: 61 })).toBe(false)
    expect(canExtrapolate({ ...AIRCRAFT, pos_age_s: null })).toBe(false)
  })
})

describe('updateMotion', () => {
  it('creates a moving aircraft from the snapshot', () => {
    const states = updateMotion([], [AIRCRAFT], null, 1000)
    expect(states).toHaveLength(1)
    expect(states[0]?.easeStart).toBeNull()
    expect(states[0]?.opacity).toBe(1)
  })

  it('eases towards the next reported position and then dead-reckons', () => {
    const first = updateMotion([], [AIRCRAFT], null, 1000)
    const second = updateMotion(first, [{ ...AIRCRAFT, lon: 17.3 }], null, 2000)

    expect(second[0]?.easeStart).toBe(2000)
    expect(second[0]?.targetLon).toBe(17.3)

    advanceMotion(second, 2750)
    expect(second[0]?.lon).toBeGreaterThan(16.3)
    expect(second[0]?.lon).toBeLessThan(17.3)

    advanceMotion(second, 3600)
    expect(second[0]?.easeStart).toBeNull()
    expect(second[0]?.lon).toBeCloseTo(17.3, 5)
  })

  it('fades and removes an aircraft after two missed snapshots', () => {
    const states = updateMotion([], [AIRCRAFT], null, 1000)
    expect(updateMotion(states, [], null, 2000)).toHaveLength(1)
    expect(updateMotion(states, [], null, 3000)).toHaveLength(1)
    expect(states[0]?.fadeStart).toBe(3000)

    advanceMotion(states, 3800)
    expect(states[0]?.opacity).toBeGreaterThan(0)
    expect(states[0]?.opacity).toBeLessThan(1)

    advanceMotion(states, 4600)
    expect(states).toHaveLength(0)
  })
})
