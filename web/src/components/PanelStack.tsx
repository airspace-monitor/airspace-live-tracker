import { TABS, type TabId } from '../lib/panels'
import { PanelContent } from './PanelContent'

interface PanelStackProps {
  active: TabId
  idPrefix: string
  onLocate?: (lon: number, lat: number) => void
}

/** All panels stay mounted so tab state and queries survive switching; inactive ones are hidden. */
export function PanelStack({ active, idPrefix, onLocate }: PanelStackProps) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {TABS.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${idPrefix}-panel-${tab.id}`}
          aria-labelledby={`${idPrefix}-tab-${tab.id}`}
          hidden={tab.id !== active}
          className="p-4"
        >
          <PanelContent tab={tab.id} onLocate={onLocate} />
        </div>
      ))}
    </div>
  )
}
