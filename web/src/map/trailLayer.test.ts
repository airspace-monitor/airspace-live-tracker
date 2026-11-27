import { describe, expect, it } from 'vitest'
import { buildTrail } from './trailLayer'

describe('buildTrail', () => {
  it('builds one segment per consecutive pair and uses the destination altitude', () => {
    const segments = buildTrail([
      [100, 16.0, 48.0, 1000],
      [160, 16.1, 48.1, null],
      [220, 16.2, 48.2, 11000],
    ])

    expect(segments).toEqual([
      { from: [16.0, 48.0], to: [16.1, 48.1], alt_m: 1000 },
      { from: [16.1, 48.1], to: [16.2, 48.2], alt_m: 11000 },
    ])
  })

  it('skips non-finite coordinates', () => {
    const segments = buildTrail([
      [100, 16.0, 48.0, 1000],
      [160, Number.NaN, 48.1, 2000],
      [220, 16.2, 48.2, 3000],
    ])
    expect(segments).toEqual([])
  })
})
