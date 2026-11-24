import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Aircraft } from '../lib/aircraft'
import { AircraftCard } from './AircraftCard'

vi.mock('../api/queries', () => ({
  useAircraft: () => ({
    data: {
      icao24: 'abc123',
      callsign: 'AUA1',
      registration: 'OE-LBA',
      typecode: 'A320',
      operator: 'Austrian',
      airline: 'Austrian Airlines',
      last_state: {
        time: '2026-11-24T12:00:00Z',
        lon: 16.3,
        lat: 48.2,
        alt_m: 10000,
        vel_ms: 200,
        track_deg: 90,
        vrate_ms: 5,
        pos_age_s: 2,
      },
      flight: {
        flight_id: '00000000-0000-0000-0000-000000000000',
        first_seen: null,
        dep_icao: 'LOWW',
        dep_source: 'opensky',
      },
      destination: null,
      eta: null,
    },
    isPending: false,
    isError: false,
  }),
}))

const AIRCRAFT: Aircraft = {
  icao24: 'abc123',
  callsign: 'AUA1',
  lon: 16.3,
  lat: 48.2,
  alt_m: 10000,
  vel_ms: 200,
  track_deg: 90,
  vrate_ms: 5,
  on_ground: false,
  pos_age_s: 2,
}

describe('AircraftCard', () => {
  it('shows the identity, units and honest M4 placeholders', () => {
    render(<AircraftCard aircraft={AIRCRAFT} onClose={vi.fn()} />)

    expect(screen.getByText('AUA1')).toBeInTheDocument()
    expect(screen.getByText('A320 · OE-LBA · Austrian Airlines')).toBeInTheDocument()
    expect(screen.getByText('32,808 ft')).toBeInTheDocument()
    expect(screen.getByText('389 kt')).toBeInTheDocument()
    expect(screen.getByText('+984 fpm')).toBeInTheDocument()
    expect(screen.getByText('LOWW')).toBeInTheDocument()
    expect(screen.getByText('Estimate arrives in M4')).toBeInTheDocument()
  })

  it('closes from the button', () => {
    const onClose = vi.fn()
    render(<AircraftCard aircraft={AIRCRAFT} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: 'Close aircraft card' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
