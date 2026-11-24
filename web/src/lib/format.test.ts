import { describe, expect, it } from 'vitest'
import {
  formatAge,
  formatCount,
  formatEventKind,
  formatFeet,
  formatKnots,
  formatUtcTime,
  formatVerticalRate,
  snapshotAgeSeconds,
} from './format'

describe('formatCount', () => {
  it('groups thousands', () => {
    expect(formatCount(10943)).toBe('10,943')
  })
})

describe('snapshotAgeSeconds', () => {
  const now = Date.parse('2026-11-22T16:08:00Z')

  it('rounds to whole seconds', () => {
    expect(snapshotAgeSeconds('2026-11-22T16:07:25Z', now)).toBe(35)
  })

  it('handles missing and invalid timestamps', () => {
    expect(snapshotAgeSeconds(null, now)).toBeNull()
    expect(snapshotAgeSeconds('not-a-date', now)).toBeNull()
  })

  it('never returns a negative age', () => {
    expect(snapshotAgeSeconds('2026-11-22T16:09:00Z', now)).toBe(0)
  })
})

describe('formatAge', () => {
  it('uses seconds, minutes and hours', () => {
    expect(formatAge(34)).toBe('34 s ago')
    expect(formatAge(180)).toBe('3 min ago')
    expect(formatAge(7200)).toBe('2 h ago')
  })

  it('handles no data', () => {
    expect(formatAge(null)).toBe('no data')
  })
})

describe('formatUtcTime', () => {
  it('renders the UTC clock time', () => {
    expect(formatUtcTime('2026-11-18T16:58:30Z')).toBe('16:58:30 UTC')
  })

  it('returns invalid input unchanged', () => {
    expect(formatUtcTime('nope')).toBe('nope')
  })
})

describe('formatEventKind', () => {
  it('humanises snake_case kinds', () => {
    expect(formatEventKind('collector_gap')).toBe('collector gap')
  })
})

describe('aircraft units', () => {
  it('converts SI to feet, knots and feet per minute', () => {
    expect(formatFeet(10000)).toBe('32,808 ft')
    expect(formatKnots(200)).toBe('389 kt')
    expect(formatVerticalRate(5)).toBe('+984 fpm')
    expect(formatVerticalRate(-5)).toBe('-984 fpm')
    expect(formatVerticalRate(0)).toBe('0 fpm')
  })

  it('shows an em dash for missing values', () => {
    expect(formatFeet(null)).toBe('—')
    expect(formatKnots(null)).toBe('—')
    expect(formatVerticalRate(null)).toBe('—')
  })
})
