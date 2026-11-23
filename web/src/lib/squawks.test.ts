import { describe, expect, it } from 'vitest'
import { squawkCodeFromKind, squawkMeaning } from './squawks'

describe('squawkMeaning', () => {
  it('explains the three emergency codes', () => {
    expect(squawkMeaning('7500')).toMatch(/hijack/i)
    expect(squawkMeaning('7600')).toMatch(/radio/i)
    expect(squawkMeaning('7700')).toMatch(/emergency/i)
  })

  it('returns undefined for an unknown code', () => {
    expect(squawkMeaning('1200')).toBeUndefined()
  })
})

describe('squawkCodeFromKind', () => {
  it('extracts the code from a squawk event kind', () => {
    expect(squawkCodeFromKind('squawk_7500')).toBe('7500')
  })

  it('ignores other event kinds', () => {
    expect(squawkCodeFromKind('go_around')).toBeNull()
    expect(squawkCodeFromKind('collector_gap')).toBeNull()
  })
})
