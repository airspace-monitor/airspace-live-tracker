const BANDS = [
  { label: 'On ground', color: '#7d8799' },
  { label: '< 3,000 m', color: '#fff1a8' },
  { label: '3,000–7,000 m', color: '#f2b84b' },
  { label: '7,000–10,000 m', color: '#e0703a' },
  { label: '> 10,000 m', color: '#c0447a' },
]

export function AltitudeLegend() {
  return (
    <div
      className="absolute bottom-3 right-3 hidden rounded-lg border border-border bg-panel/90 p-2.5 text-[11px] text-muted lg:block"
      aria-label="Altitude bands"
    >
      <p className="mb-1.5 font-mono text-[9px] uppercase tracking-wider">Altitude</p>
      <ul className="space-y-1">
        {BANDS.map((band) => (
          <li key={band.label} className="flex items-center gap-2">
            <span
              className="h-2 w-2 rounded-sm"
              style={{ backgroundColor: band.color }}
              aria-hidden="true"
            />
            <span>{band.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
