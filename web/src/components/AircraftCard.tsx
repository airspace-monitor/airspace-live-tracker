import { useAircraft } from '../api/queries'
import type { Aircraft } from '../lib/aircraft'
import { formatFeet, formatKnots, formatUtcTime, formatVerticalRate } from '../lib/format'

interface AircraftCardProps {
  aircraft: Aircraft
  onClose: () => void
}

export function AircraftCard({ aircraft, onClose }: AircraftCardProps) {
  const { data, isPending, isError } = useAircraft(aircraft.icao24)
  const state = data?.last_state
  const callsign = data?.callsign ?? aircraft.callsign ?? aircraft.icao24.toUpperCase()
  const meta = [data?.typecode, data?.registration, data?.airline ?? data?.operator]
    .filter(Boolean)
    .join(' · ')

  return (
    <section
      aria-label={`Aircraft ${callsign}`}
      className="absolute left-3 top-12 z-30 max-h-[calc(100%-4rem)] w-72 max-w-[calc(100%-1.5rem)] overflow-y-auto rounded-lg border border-border bg-panel p-3 shadow-2xl"
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate font-mono text-lg font-semibold leading-tight">{callsign}</h2>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted">
            {aircraft.icao24}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close aircraft card"
          className="rounded p-1 text-muted hover:bg-border/40 hover:text-text"
        >
          ✕
        </button>
      </header>

      <p className="mt-1.5 truncate text-[11px] text-muted">
        {meta || (isPending ? 'Loading details…' : 'No type/registration data yet')}
      </p>

      <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-border pt-2">
        <div>
          <dt className="font-mono text-[9px] uppercase tracking-wider text-muted">Altitude</dt>
          <dd className="mt-0.5 font-mono text-xs text-text">
            {formatFeet(state?.alt_m ?? aircraft.alt_m)}
          </dd>
        </div>
        <div>
          <dt className="font-mono text-[9px] uppercase tracking-wider text-muted">Speed</dt>
          <dd className="mt-0.5 font-mono text-xs text-text">
            {formatKnots(state?.vel_ms ?? aircraft.vel_ms)}
          </dd>
        </div>
        <div>
          <dt className="font-mono text-[9px] uppercase tracking-wider text-muted">V/S</dt>
          <dd className="mt-0.5 font-mono text-xs text-text">
            {formatVerticalRate(state?.vrate_ms ?? aircraft.vrate_ms)}
          </dd>
        </div>
      </dl>

      {data?.flight?.dep_icao ? (
        <p className="mt-2 text-[11px] text-muted">
          From <span className="font-mono text-text">{data.flight.dep_icao}</span>
        </p>
      ) : null}

      <div className="mt-3 space-y-2 border-t border-border pt-2">
        <div>
          <p className="font-mono text-[9px] uppercase tracking-wider text-muted">
            Likely destination
          </p>
          {data?.destination ? (
            <ul className="mt-1 space-y-1">
              {data.destination.candidates.slice(0, 3).map((candidate) => (
                <li key={candidate.icao} className="flex items-center gap-2 text-[11px]">
                  <span className="w-10 font-mono text-text">{candidate.icao}</span>
                  <span className="h-1 flex-1 overflow-hidden rounded-full bg-border">
                    <span
                      className="block h-full rounded-full bg-accent"
                      style={{ width: `${Math.round(candidate.p * 100)}%` }}
                    />
                  </span>
                  <span className="w-8 text-right font-mono text-[10px] text-muted">
                    {Math.round(candidate.p * 100)}%
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-0.5 text-[11px] text-muted">Estimate arrives in M4</p>
          )}
        </div>

        <div>
          <p className="font-mono text-[9px] uppercase tracking-wider text-muted">ETA</p>
          {data?.eta ? (
            <p className="mt-0.5 font-mono text-[11px] text-text">
              {formatUtcTime(data.eta.p50)}{' '}
              <span className="text-muted">
                ({formatUtcTime(data.eta.p10)}–{formatUtcTime(data.eta.p90)})
              </span>
            </p>
          ) : (
            <p className="mt-0.5 text-[11px] text-muted">—</p>
          )}
        </div>
      </div>

      {isError ? (
        <p className="mt-2 text-[10px] text-warn">
          Details unavailable; showing the last snapshot.
        </p>
      ) : null}
    </section>
  )
}
