import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { squawkMeaning } from '../lib/squawks'

interface SquawkCodeProps {
  code: string
}

/**
 * The number of an emergency squawk code, with its meaning on hover or keyboard focus.
 * Rendered in a portal so the Events panel's scroll container cannot clip the tooltip.
 */
export function SquawkCode({ code }: SquawkCodeProps) {
  const meaning = squawkMeaning(code)
  const id = useId()
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null)

  useEffect(() => {
    if (!position) return
    const hideOnScroll = () => setPosition(null)
    window.addEventListener('scroll', hideOnScroll, true)
    return () => window.removeEventListener('scroll', hideOnScroll, true)
  }, [position])

  if (!meaning) return <span className="font-mono">{code}</span>

  const show = () => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const width = 240
    const left = Math.min(Math.max(8, rect.left - 8), window.innerWidth - width - 8)
    const top = rect.bottom + 76 > window.innerHeight ? rect.top - 72 : rect.bottom + 6
    setPosition({ top, left })
  }

  const hide = () => setPosition(null)

  return (
    <span
      ref={triggerRef}
      tabIndex={0}
      aria-describedby={id}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      onKeyDown={(event) => {
        if (event.key === 'Escape') hide()
      }}
      className="cursor-help rounded-sm font-mono underline decoration-dotted decoration-border underline-offset-2"
    >
      <span>{code}</span>

      {position ? (
        createPortal(
          <span
            role="tooltip"
            id={id}
            style={{ top: position.top, left: position.left }}
            className="pointer-events-none fixed z-50 block w-60 rounded-md border border-border bg-bg px-2.5 py-2 text-[11px] tracking-normal text-text shadow-xl"
          >
            <span className="block font-semibold">Squawk {code}</span>
            <span className="text-muted">{meaning}</span>
          </span>,
          document.body,
        )
      ) : (
        <span id={id} className="sr-only">
          {meaning}
        </span>
      )}
    </span>
  )
}
