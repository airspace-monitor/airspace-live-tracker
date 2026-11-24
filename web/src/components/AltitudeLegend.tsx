import { ALTITUDE_BANDS } from '../lib/altitude'

export function AltitudeLegend() {
  return (
    <div
      className="absolute bottom-3 right-3 z-20 hidden rounded-lg border border-border bg-panel p-2.5 text-[11px] text-muted lg:block"
      aria-label="Altitude bands"
    >
      <p className="mb-1.5 font-mono text-[9px] uppercase tracking-wider">Altitude</p>
      <ul className="space-y-1">
        {ALTITUDE_BANDS.map((band) => (
          <li key={band.label} className="flex items-center gap-2">
            <span
              className="h-2 w-2 rounded-sm"
              style={{ backgroundColor: band.hex }}
              aria-hidden="true"
            />
            <span>{band.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
