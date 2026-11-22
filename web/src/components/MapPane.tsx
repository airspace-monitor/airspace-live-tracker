import { AltitudeLegend } from './AltitudeLegend'

/**
 * Placeholder for the real map (M2.5). Kept in its own module so it stays a lazy
 * chunk: MapLibre + deck.gl must not enter the app shell bundle.
 */
export default function MapPane() {
  return (
    <div className="relative h-full w-full overflow-hidden bg-bg">
      <div
        className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,#151d33_0%,#0b1020_70%)]"
        aria-hidden="true"
      />
      <div className="map-grid absolute inset-0 opacity-50" aria-hidden="true" />

      <div className="absolute left-3 top-3 rounded border border-border bg-panel/80 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted">
        Europe · zoom 4
      </div>

      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center">
        <span className="rounded-full border border-border bg-panel/80 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
          Live map · M2.5
        </span>
        <p className="max-w-xs text-sm text-muted">
          Aircraft positions, altitude colours and smooth motion arrive in the next milestone.
        </p>
      </div>

      <AltitudeLegend />
    </div>
  )
}
