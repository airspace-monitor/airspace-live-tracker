import { PathLayer, ScatterplotLayer } from '@deck.gl/layers'
import { altitudeColor } from '../lib/altitude'
import type { TrackPoint } from '../api/types'
import type { MotionAircraft } from './motion'

export interface TrailSegment {
  from: [number, number]
  to: [number, number]
  alt_m: number | null
}

/** Turn track points into per-segment paths so each segment gets its own altitude colour. */
export function buildTrail(points: TrackPoint[]): TrailSegment[] {
  const segments: TrailSegment[] = []
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1]
    const current = points[index]
    if (!previous || !current) continue
    const [, fromLon, fromLat, fromAlt] = previous
    const [, toLon, toLat, toAlt] = current
    if (![fromLon, fromLat, toLon, toLat].every(Number.isFinite)) continue
    segments.push({
      from: [fromLon, fromLat],
      to: [toLon, toLat],
      alt_m: toAlt ?? fromAlt,
    })
  }
  return segments
}

export function trailLayer(segments: TrailSegment[]) {
  return new PathLayer<TrailSegment>({
    id: 'selected-trail',
    data: segments,
    getPath: (segment) => [segment.from, segment.to],
    getColor: (segment): [number, number, number, number] => altitudeColor(segment.alt_m, false, 0),
    getWidth: 2,
    widthUnits: 'pixels',
    widthMinPixels: 2,
    widthMaxPixels: 3,
    capRounded: true,
    jointRounded: true,
    opacity: 0.9,
    pickable: false,
  })
}

/** The docs/08 2 px accent halo around the selected aircraft. */
export function selectedHaloLayer(aircraft: MotionAircraft | null) {
  return new ScatterplotLayer<MotionAircraft>({
    id: 'selected-halo',
    data: aircraft ? [aircraft] : [],
    getPosition: (row) => [row.lon, row.lat],
    getRadius: 12,
    radiusUnits: 'pixels',
    stroked: true,
    filled: false,
    getLineColor: [76, 195, 255, 255],
    getLineWidth: 2,
    lineWidthUnits: 'pixels',
    pickable: false,
  })
}
