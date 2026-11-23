/**
 * ICAO emergency squawk codes carried by the stream-worker event kinds
 * (docs/04-pipelines.md). 7500/7600/7700 are the three standard emergency codes.
 */
const MEANINGS: Record<string, string> = {
  '7500': 'Unlawful interference (hijacking)',
  '7600': 'Radio communication failure',
  '7700': 'General emergency',
}

export function squawkMeaning(code: string): string | undefined {
  return MEANINGS[code]
}

/** `squawk_7500` -> `7500`; null for every other event kind. */
export function squawkCodeFromKind(kind: string): string | null {
  const match = /^squawk_(\d{4})$/.exec(kind)
  return match?.[1] ?? null
}
