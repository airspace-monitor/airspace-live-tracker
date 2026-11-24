import { IconLayer } from '@deck.gl/layers'
import type { Aircraft } from '../lib/aircraft'
import { altitudeColor } from '../lib/altitude'
import { PLANE_ICON_ATLAS, PLANE_ICON_MAPPING } from '../lib/planeIcon'

/**
 * One plane per live state, rotated by its track and tinted by altitude band.
 * deck.gl's native autoHighlight gives an immediate hover colour; the callback
 * only mirrors the hover state onto the map cursor.
 */
export function aircraftLayer(
  aircraft: Aircraft[],
  onHoverChange?: (icao24: string | null) => void,
) {
  return new IconLayer<Aircraft>({
    id: 'aircraft',
    data: aircraft,
    iconAtlas: PLANE_ICON_ATLAS,
    iconMapping: PLANE_ICON_MAPPING,
    getIcon: () => 'plane',
    getPosition: (d): [number, number] => [d.lon, d.lat],
    getSize: 16,
    sizeUnits: 'pixels',
    getColor: (d) => altitudeColor(d.alt_m, d.on_ground, d.pos_age_s),
    getAngle: (d) => d.track_deg ?? 0,
    pickable: true,
    autoHighlight: true,
    highlightColor: [76, 195, 255, 160],
    onHover: (info) => {
      onHoverChange?.((info.object as Aircraft | undefined)?.icao24 ?? null)
    },
  })
}
