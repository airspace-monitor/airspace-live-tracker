import { PlaceholderPanel } from './PlaceholderPanel'

export function BriefingPanel() {
  return (
    <PlaceholderPanel
      eyebrow="Briefing"
      title="AI airspace briefing"
      description="A short, factual summary of the airspace, regenerated every 30 minutes from the database."
      eta="M5"
    >
      <ul className="space-y-1 text-xs leading-relaxed text-muted">
        <li>Traffic volume and unusually busy or quiet areas</li>
        <li>Notable events and collection gaps</li>
        <li>A countdown to the next briefing</li>
      </ul>
    </PlaceholderPanel>
  )
}
