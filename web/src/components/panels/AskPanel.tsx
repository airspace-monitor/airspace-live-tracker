import { PlaceholderPanel } from './PlaceholderPanel'

const EXAMPLES = [
  'How busy is it right now?',
  'Which airport is busiest today?',
  'Were there any collection gaps?',
]

export function AskPanel() {
  return (
    <PlaceholderPanel
      eyebrow="Ask"
      title="Ask the airspace"
      description="Plain-English questions answered from the database, with the SQL behind every answer."
      eta="M5"
    >
      <label htmlFor="ask-preview" className="sr-only">
        Question
      </label>
      <input
        id="ask-preview"
        type="text"
        disabled
        maxLength={500}
        placeholder="Which airline had the most arrivals into Vienna yesterday?"
        className="w-full rounded-md border border-border bg-bg/60 px-3 py-2 text-sm text-text placeholder:text-muted/70 disabled:cursor-not-allowed"
      />
      <div className="flex flex-wrap gap-1.5">
        {EXAMPLES.map((example) => (
          <span
            key={example}
            className="rounded-full border border-border px-2.5 py-1 text-[11px] text-muted"
          >
            {example}
          </span>
        ))}
      </div>
    </PlaceholderPanel>
  )
}
