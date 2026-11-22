import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Header } from './Header'

vi.mock('../api/queries', () => ({
  useStats: () => ({
    data: {
      aircraft_now: 10_943,
      snapshot_time: new Date().toISOString(),
      collectors_online: 1,
      rows_today: 4_610_732,
      dq_status: null,
    },
    isPending: false,
    isError: false,
  }),
}))

describe('Header', () => {
  it('shows the live counts from /stats', () => {
    render(<Header />)

    expect(screen.getByText('10,943')).toBeInTheDocument()
    expect(
      screen.getByText((_, element) => element?.textContent === '1/1 collectors'),
    ).toBeInTheDocument()
    expect(screen.getByText(/snapshot/)).toBeInTheDocument()
  })
})
