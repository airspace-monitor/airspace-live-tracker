/**
 * Panel order follows docs/08-frontend.md. Events is the default because it is the
 * only panel with real data today; switch to Briefing once M5 lands.
 */
export const TABS = [
  { id: 'briefing', label: 'Briefing' },
  { id: 'ask', label: 'Ask' },
  { id: 'arrivals', label: 'Arrivals' },
  { id: 'events', label: 'Events' },
] as const

export type TabId = (typeof TABS)[number]['id']

export const DEFAULT_TAB: TabId = 'events'
