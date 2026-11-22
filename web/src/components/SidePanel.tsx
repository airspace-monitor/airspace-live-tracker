import type { TabId } from '../lib/panels'
import { PanelStack } from './PanelStack'
import { Tabs } from './Tabs'

interface SidePanelProps {
  active: TabId
  onChange: (tab: TabId) => void
}

export function SidePanel({ active, onChange }: SidePanelProps) {
  return (
    <aside className="flex min-h-0 flex-col border-l border-border bg-panel">
      <Tabs active={active} onChange={onChange} idPrefix="side" />
      <PanelStack active={active} idPrefix="side" />
    </aside>
  )
}
