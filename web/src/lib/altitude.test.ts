import { describe, expect, it } from 'vitest'
import { altitudeColor } from './altitude'

describe('altitudeColor', () => {
  it('uses the ground colour when on the ground or without altitude', () => {
    expect(altitudeColor(0, true, 0)).toEqual([125, 135, 153, 255])
    expect(altitudeColor(null, false, 0)).toEqual([125, 135, 153, 255])
  })

  it('maps the four airborne bands', () => {
    expect(altitudeColor(1000, false, 0)).toEqual([255, 241, 168, 255])
    expect(altitudeColor(3000, false, 0)).toEqual([242, 184, 75, 255])
    expect(altitudeColor(7000, false, 0)).toEqual([224, 112, 58, 255])
    expect(altitudeColor(10000, false, 0)).toEqual([224, 112, 58, 255])
    expect(altitudeColor(10001, false, 0)).toEqual([192, 68, 122, 255])
  })

  it('draws stale positions at 50% opacity', () => {
    expect(altitudeColor(10000, false, 61)[3]).toBe(128)
    expect(altitudeColor(10000, false, 60)[3]).toBe(255)
  })
})
