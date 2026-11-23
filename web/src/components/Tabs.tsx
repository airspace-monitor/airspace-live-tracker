import { useRef, type KeyboardEvent } from 'react'
import { TABS, type TabId } from '../lib/panels'

interface TabsProps {
  active: TabId
  onChange: (tab: TabId) => void
  idPrefix: string
}

export function Tabs({ active, onChange, idPrefix }: TabsProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])

  const move = (index: number) => {
    const tab = TABS[index]
    if (!tab) return
    onChange(tab.id)
    refs.current[index]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      move((index + 1) % TABS.length)
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      move((index - 1 + TABS.length) % TABS.length)
    } else if (event.key === 'Home') {
      event.preventDefault()
      move(0)
    } else if (event.key === 'End') {
      event.preventDefault()
      move(TABS.length - 1)
    }
  }

  return (
    <div
      role="tablist"
      aria-label="Panels"
      className="flex shrink-0 overflow-x-auto border-b border-border px-2"
    >
      {TABS.map((tab, index) => {
        const selected = tab.id === active
        return (
          <button
            key={tab.id}
            ref={(node) => {
              refs.current[index] = node
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`-mb-px shrink-0 border-b-2 px-2.5 py-2.5 text-[11px] font-medium uppercase tracking-wider transition-colors ${
              selected ? 'border-accent text-text' : 'border-transparent text-muted hover:text-text'
            }`}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
