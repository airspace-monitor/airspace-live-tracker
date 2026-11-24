import { describe, expect, it } from 'vitest'
import type { Snapshot } from '../api/types'
import { parseAircraft } from './aircraft'

const SNAPSHOT: Snapshot = {
  snapshot_time: '2026-11-24T11:00:00Z',
  next_expected_at: '2026-11-24T11:01:30Z',
  fields: [
    'icao24',
    'callsign',
    'lon',
    'lat',
    'alt_m',
    'vel_ms',
    'track_deg',
    'vrate_ms',
    'on_ground',
    'pos_age_s',
  ],
  states: [
    ['abc123', ' AUA1 ', 16.3, 48.2, 10300, 230, 90, 0, false, 3],
    ['def456', null, null, 48.1, 1000, 0, 0, 0, true, 2],
    ['ghi789', '', 16.1, 48.0, null, null, null, null, null, null],
    ['jkl012', 'DLH2', 0, 0, 0, 0, 0, 0, false, 90],
  ],
}

describe('parseAircraft', () => {
  it('drops states without a position and trims callsigns', () => {
    const aircraft = parseAircraft(SNAPSHOT)

    expect(aircraft).toHaveLength(3)
    expect(aircraft[0]).toMatchObject({
      icao24: 'abc123',
      callsign: 'AUA1',
      lon: 16.3,
      lat: 48.2,
      alt_m: 10300,
    })
    expect(aircraft[1]?.callsign).toBeNull()
    expect(aircraft[2]?.callsign).toBe('DLH2')
  })

  it('keeps zero-degree coordinates and maps missing values to null', () => {
    const aircraft = parseAircraft(SNAPSHOT)

    expect(aircraft[1]?.alt_m).toBeNull()
    expect(aircraft[2]).toMatchObject({ lon: 0, lat: 0, alt_m: 0, pos_age_s: 90 })
    expect(aircraft[0]?.pos_age_s).toBe(3)
  })
})
