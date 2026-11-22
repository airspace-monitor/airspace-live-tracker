import { useState } from 'react'
import type { TabId } from '../lib/panels'
import { PanelStack } from './PanelStack'
import { Tabs } from './Tabs'

interface BottomSheetProps {
  active: TabId
  onChange: (tab: TabId) => void
}

/** The under-900px layout: the side panel becomes a collapsible sheet above the footer. */
export function BottomSheet({ active, onChange }: BottomSheetProps) {
  const [expanded, setExpanded] = useState(true)

  return (
    <section
      aria-label="Panels"
      className={`absolute inset-x-0 bottom-0 z-20 flex flex-col overflow-hidden rounded-t-2xl border-t border-border bg-panel shadow-2xl transition-[height] duration-200 ${
        expanded ? 'h-[46%] min-h-60' : 'h-16'
      }`}
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-controls="sheet-panels"
        aria-label={expanded ? 'Collapse panels' : 'Expand panels'}
        className="flex h-6 w-full shrink-0 items-center justify-center"
      >
        <span className="h-1 w-10 rounded-full bg-border" />
      </button>

      <Tabs active={active} onChange={onChange} idPrefix="sheet" />

      <div id="sheet-panels" className="min-h-0 flex-1" hidden={!expanded}>
        <PanelStack active={active} idPrefix="sheet" />
      </div>
    </section>
  )
}
