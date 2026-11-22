import type { EventSeverity } from '../../api/types'
import { useEvents } from '../../api/queries'
import { formatEventKind, formatUtcTime } from '../../lib/format'

const SEVERITY_STYLES: Record<EventSeverity, string> = {
  info: 'border-border text-muted',
  warn: 'border-warn/40 text-warn',
  alert: 'border-alert/40 text-alert',
}

export function EventsPanel() {
  const { data, isPending, isError, refetch } = useEvents()

  if (isPending) {
    return <p className="animate-pulse text-sm text-muted">Loading events…</p>
  }

  if (isError) {
    return (
      <div className="space-y-2 text-sm text-muted">
        <p>Could not load events.</p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="rounded border border-border px-2 py-1 text-xs text-text hover:border-accent"
        >
          Retry
        </button>
      </div>
    )
  }

  const events = data?.events ?? []

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">Events</p>
          <h2 className="text-base font-semibold">Live feed</h2>
        </div>
        <span className="font-mono text-[11px] text-muted">{events.length} latest</span>
      </div>

      {events.length === 0 ? (
        <p className="text-sm text-muted">No events yet. Collection gaps appear here first.</p>
      ) : (
        <ul className="divide-y divide-border">
          {events.map((event) => {
            const detail = [event.icao24?.toUpperCase(), event.airport_icao]
              .filter((value): value is string => Boolean(value))
              .join(' · ')
            return (
              <li key={event.event_id} className="py-2.5">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider">
                  <span
                    className={`rounded border px-1.5 py-0.5 font-mono ${SEVERITY_STYLES[event.severity]}`}
                  >
                    {event.severity}
                  </span>
                  <span className="truncate text-muted">{formatEventKind(event.kind)}</span>
                  <time dateTime={event.ts} className="ml-auto shrink-0 font-mono text-muted">
                    {formatUtcTime(event.ts)}
                  </time>
                </div>
                <p className="mt-1 text-sm leading-snug">{event.title}</p>
                {detail ? (
                  <p className="mt-0.5 font-mono text-[10px] text-muted">{detail}</p>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}

      <p className="border-t border-border pt-2 text-[11px] text-muted">
        Cursor paging and map fly-to arrive in M2.6.
      </p>
    </section>
  )
}
