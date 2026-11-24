const countFormat = new Intl.NumberFormat('en-GB')

export function formatCount(value: number): string {
  return countFormat.format(value)
}

/** Whole seconds between a snapshot timestamp and `nowMs`; null when there is no valid time. */
export function snapshotAgeSeconds(snapshotTime: string | null, nowMs: number): number | null {
  if (snapshotTime === null) return null
  const parsed = Date.parse(snapshotTime)
  if (Number.isNaN(parsed)) return null
  return Math.max(0, Math.round((nowMs - parsed) / 1000))
}

export function formatAge(seconds: number | null): string {
  if (seconds === null) return 'no data'
  if (seconds < 120) return `${seconds} s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 120) return `${minutes} min ago`
  return `${Math.round(minutes / 60)} h ago`
}

/** "16:58:30 UTC"; timestamps are always rendered in UTC (docs/09-conventions.md). */
export function formatUtcTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return `${date.toISOString().slice(11, 19)} UTC`
}

export function formatEventKind(kind: string): string {
  return kind.replaceAll('_', ' ')
}

const FT_PER_M = 3.280839895
const KT_PER_MS = 1.943844492
const FPM_PER_MS = 196.8503937

export function formatFeet(altM: number | null): string {
  return altM === null ? '—' : `${countFormat.format(Math.round(altM * FT_PER_M))} ft`
}

export function formatKnots(velMs: number | null): string {
  return velMs === null ? '—' : `${countFormat.format(Math.round(velMs * KT_PER_MS))} kt`
}

export function formatVerticalRate(vrateMs: number | null): string {
  if (vrateMs === null) return '—'
  const fpm = Math.round(vrateMs * FPM_PER_MS)
  return `${fpm > 0 ? '+' : ''}${countFormat.format(fpm)} fpm`
}
