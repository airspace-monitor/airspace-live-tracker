import { describe, expect, it } from 'vitest'
import { trackToIconAngle } from './heading'

describe('trackToIconAngle', () => {
  it('converts clockwise compass tracks to counter-clockwise icon angles', () => {
    expect(trackToIconAngle(0)).toBe(0)
    expect(trackToIconAngle(90)).toBe(270)
    expect(trackToIconAngle(180)).toBe(180)
    expect(trackToIconAngle(270)).toBe(90)
  })

  it('normalizes negative and out-of-range tracks', () => {
    expect(trackToIconAngle(-90)).toBe(90)
    expect(trackToIconAngle(450)).toBe(270)
  })

  it('falls back to north for missing tracks', () => {
    expect(trackToIconAngle(null)).toBe(0)
    expect(trackToIconAngle(Number.NaN)).toBe(0)
  })
})
