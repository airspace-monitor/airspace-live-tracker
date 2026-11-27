import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { EventsPanel } from './EventsPanel'

vi.mock('../../api/queries', () => ({
  useEventsInfinite: () => ({
    data: {
      pages: [
        {
          events: [
            {
              event_id: 336,
              ts: '2026-11-18T16:58:30Z',
              kind: 'collector_gap',
              severity: 'warn',
              title: 'No data from pi-daniel since 2026-11-18 16:58 UTC',
              icao24: null,
              airport_icao: null,
              lon: null,
              lat: null,
            },
            {
              event_id: 400,
              ts: '2026-11-23T12:23:55Z',
              kind: 'squawk_7500',
              severity: 'alert',
              title: 'Squawk 7500 unlawful interference (GAM332A)',
              icao24: '3f9f9c',
              airport_icao: null,
              lon: 16.6,
              lat: 48.1,
            },
          ],
          next_cursor: null,
        },
      ],
    },
    isPending: false,
    isError: false,
    refetch: vi.fn(),
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
  }),
}))

describe('EventsPanel', () => {
  it('renders a severity, kind, UTC time and title', () => {
    render(<EventsPanel />)

    expect(
      screen.getByText('No data from pi-daniel since 2026-11-18 16:58 UTC'),
    ).toBeInTheDocument()
    expect(screen.getByText('warn')).toBeInTheDocument()
    expect(screen.getByText('collector gap')).toBeInTheDocument()
    expect(screen.getByText('16:58:30 UTC')).toBeInTheDocument()
  })

  it('explains a squawk number on hover', () => {
    render(<EventsPanel />)

    fireEvent.mouseEnter(screen.getByText('7500'))

    expect(screen.getByRole('tooltip')).toHaveTextContent('Unlawful interference (hijacking)')
  })

  it('calls onLocate for an event with coordinates', () => {
    const onLocate = vi.fn()
    render(<EventsPanel onLocate={onLocate} />)

    fireEvent.click(
      screen.getByRole('button', { name: 'Fly to Squawk 7500 unlawful interference (GAM332A)' }),
    )

    expect(onLocate).toHaveBeenCalledWith(16.6, 48.1)
  })
})
