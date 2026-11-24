import { IconLayer } from '@deck.gl/layers'
import type { Aircraft } from '../lib/aircraft'
import { altitudeColor } from '../lib/altitude'
import { PLANE_ICON_ATLAS, PLANE_ICON_MAPPING } from '../lib/planeIcon'

/**
 * One plane per live state, rotated by its track and tinted by altitude band.
 * Icon size is in CSS pixels; at ~11k aircraft the map stays readable while zoomed out.
 */
export function aircraftLayer(aircraft: Aircraft[]) {
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
  })
}
