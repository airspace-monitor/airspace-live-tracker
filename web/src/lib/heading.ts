/**
 * deck.gl's IconLayer angle is counter-clockwise from the icon's up direction,
 * while OpenSky's `track_deg` is a compass track: clockwise from north.
 * Returning the complement keeps the north-pointing plane glyph on its track.
 */
export function trackToIconAngle(trackDeg: number | null): number {
  if (trackDeg === null || !Number.isFinite(trackDeg)) return 0
  return (360 - (trackDeg % 360) + 360) % 360
}
