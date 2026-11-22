import type { ReactNode } from 'react'

interface PlaceholderPanelProps {
  eyebrow: string
  title: string
  description: string
  eta: string
  children?: ReactNode
}

export function PlaceholderPanel({
  eyebrow,
  title,
  description,
  eta,
  children,
}: PlaceholderPanelProps) {
  return (
    <section className="space-y-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">{eyebrow}</p>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="text-sm leading-relaxed text-muted">{description}</p>
      {children}
      <p className="rounded-md border border-dashed border-border px-3 py-2 text-[11px] text-muted">
        Ships in <span className="font-mono text-text">{eta}</span>.
      </p>
    </section>
  )
}
