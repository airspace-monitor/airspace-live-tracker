import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Footer } from './Footer'

describe('Footer', () => {
  it('keeps the required attribution visible', () => {
    render(<Footer />)

    expect(screen.getByText('The OpenSky Network')).toBeInTheDocument()
    expect(screen.getByText(/CARTO|OpenFreeMap/)).toBeInTheDocument()
    expect(screen.getByText('OpenStreetMap')).toBeInTheDocument()
  })
})
