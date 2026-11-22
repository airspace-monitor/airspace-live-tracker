import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Tabs } from './Tabs'

describe('Tabs', () => {
  it('marks the active tab and reports clicks', () => {
    const onChange = vi.fn()
    render(<Tabs active="events" onChange={onChange} idPrefix="test" />)

    expect(screen.getByRole('tab', { name: 'Events' })).toHaveAttribute('aria-selected', 'true')

    fireEvent.click(screen.getByRole('tab', { name: 'Briefing' }))
    expect(onChange).toHaveBeenCalledWith('briefing')
  })

  it('moves selection with the arrow keys', () => {
    const onChange = vi.fn()
    render(<Tabs active="events" onChange={onChange} idPrefix="test" />)

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Events' }), { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenCalledWith('arrivals')
  })
})
