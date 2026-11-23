import type { TabId } from '../lib/panels'
import { ArrivalsPanel } from './panels/ArrivalsPanel'
import { AskPanel } from './panels/AskPanel'
import { BriefingPanel } from './panels/BriefingPanel'
import { EventsPanel } from './panels/EventsPanel'

export function PanelContent({ tab }: { tab: TabId }) {
  switch (tab) {
    case 'briefing':
      return <BriefingPanel />
    case 'ask':
      return <AskPanel />
    case 'arrivals':
      return <ArrivalsPanel />
    case 'events':
      return <EventsPanel />
  }
}
