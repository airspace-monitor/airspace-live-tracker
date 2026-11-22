import { useStats } from '../api/queries'
import { useNow } from '../hooks/useNow'
import { EXPECTED_COLLECTORS, STALE_AFTER_SECONDS } from '../lib/config'
import { formatAge, formatCount, snapshotAgeSeconds } from '../lib/format'

export function Header() {
  const { data, isPending, isError } = useStats()
  const now = useNow()
  const age = snapshotAgeSeconds(data?.snapshot_time ?? null, now)
  const stale = age !== null && age > STALE_AFTER_SECONDS

  return (
    <header className="z-10 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-panel px-3 sm:px-4">
      <div className="flex min-w-0 items-center gap-2">
        <DiamondMark />
        <span className="truncate text-sm font-semibold tracking-tight sm:text-base">
          Airspace Monitor
        </span>
      </div>

      <div className="flex items-center gap-2 whitespace-nowrap font-mono text-[11px] text-muted sm:gap-3 sm:text-xs">
        {isPending ? <span className="animate-pulse">connecting…</span> : null}
        {isError ? <span className="text-warn">API offline</span> : null}
        {data ? (
          <>
            <span>
              <span className="text-text">{formatCount(data.aircraft_now)}</span> aircraft
            </span>
            <span aria-hidden="true" className="text-border">
              ·
            </span>
            <span title={stale ? 'No snapshot in the last 5 minutes' : undefined}>
              snapshot <span className={stale ? 'text-warn' : 'text-text'}>{formatAge(age)}</span>
            </span>
            <span aria-hidden="true" className="hidden text-border sm:inline">
              ·
            </span>
            <span className="hidden sm:inline">
              <span className={data.collectors_online === 0 ? 'text-warn' : 'text-text'}>
                {data.collectors_online}
              </span>
              /{EXPECTED_COLLECTORS} collectors
            </span>
          </>
        ) : null}
      </div>
    </header>
  )
}

function DiamondMark() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true">
      <path d="M8 1l7 7-7 7-7-7z" fill="currentColor" />
    </svg>
  )
}
