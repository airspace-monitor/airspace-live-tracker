import { PlaceholderPanel } from './PlaceholderPanel'

const AIRPORTS = ['VIE', 'BTS', 'BUD']

export function ArrivalsPanel() {
  return (
    <PlaceholderPanel
      eyebrow="Arrivals"
      title="Arrivals board"
      description="Arrival estimates for Vienna, Bratislava and Budapest, shown as a p10–p90 range."
      eta="M4"
    >
      <div className="flex gap-1" aria-label="Airports">
        {AIRPORTS.map((code, index) => (
          <span
            key={code}
            className={`rounded px-2 py-1 font-mono text-[11px] ${
              index === 0 ? 'bg-accent/15 text-accent' : 'text-muted'
            }`}
          >
            {code}
          </span>
        ))}
      </div>
      <div className="flex items-center justify-between border-t border-border pt-2 font-mono text-[10px] uppercase tracking-wider text-muted">
        <span>callsign · from</span>
        <span>ETA</span>
      </div>
      <p className="py-3 text-center text-xs text-muted">No predictions yet.</p>
    </PlaceholderPanel>
  )
}
