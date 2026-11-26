import { IconLayer } from '@deck.gl/layers'
import { altitudeColor } from '../lib/altitude'
import { PLANE_ICON_ATLAS, PLANE_ICON_MAPPING } from '../lib/planeIcon'
import type { MotionAircraft } from './motion'

/**
 * One plane per live state, rotated by its track and tinted by altitude band.
 * `revision` changes every animation frame so deck.gl rebuilds the position and
 * colour buffers for the interpolated positions. Native autoHighlight keeps the
 * hover colour immediate; the callback only mirrors it onto the map cursor.
 */
export function aircraftLayer(
  aircraft: MotionAircraft[],
  onHoverChange?: (icao24: string | null) => void,
  revision = 0,
) {
  return new IconLayer<MotionAircraft>({
    id: 'aircraft',
    data: aircraft,
    iconAtlas: PLANE_ICON_ATLAS,
    iconMapping: PLANE_ICON_MAPPING,
    getIcon: () => 'plane',
    getPosition: (d): [number, number] => [d.lon, d.lat],
    getSize: 16,
    sizeUnits: 'pixels',
    getColor: (d): [number, number, number, number] => {
      const [r, g, b, alpha] = altitudeColor(d.alt_m, d.on_ground, d.pos_age_s)
      return [r, g, b, Math.round(alpha * d.opacity)]
    },
    getAngle: (d) => d.track_deg ?? 0,
    pickable: true,
    autoHighlight: true,
    highlightColor: [76, 195, 255, 160],
    updateTriggers: {
      getPosition: [revision],
      getColor: [revision],
    },
    onHover: (info) => {
      onHoverChange?.((info.object as MotionAircraft | undefined)?.icao24 ?? null)
    },
  })
}
