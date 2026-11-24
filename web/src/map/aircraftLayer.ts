import { IconLayer } from '@deck.gl/layers'
import type { Aircraft } from '../lib/aircraft'
import { altitudeColor } from '../lib/altitude'
import { PLANE_ICON_ATLAS, PLANE_ICON_MAPPING } from '../lib/planeIcon'

/**
 * One plane per live state, rotated by its track and tinted by altitude band.
 * The hovered aircraft is recoloured accent blue instead of using deck.gl
 * autoHighlight, which picks on every pointer move.
 */
export function aircraftLayer(aircraft: Aircraft[], hoveredIcao24: string | null = null) {
  return new IconLayer<Aircraft>({
    id: 'aircraft',
    data: aircraft,
    iconAtlas: PLANE_ICON_ATLAS,
    iconMapping: PLANE_ICON_MAPPING,
    getIcon: () => 'plane',
    getPosition: (d): [number, number] => [d.lon, d.lat],
    getSize: (d) => (d.icao24 === hoveredIcao24 ? 20 : 16),
    sizeUnits: 'pixels',
    getColor: (d) =>
      d.icao24 === hoveredIcao24
        ? [76, 195, 255, 255]
        : altitudeColor(d.alt_m, d.on_ground, d.pos_age_s),
    getAngle: (d) => d.track_deg ?? 0,
    pickable: true,
    // External state changes must invalidate deck.gl's accessor buffers.
    updateTriggers: {
      getColor: [hoveredIcao24],
      getSize: [hoveredIcao24],
    },
  })
}
