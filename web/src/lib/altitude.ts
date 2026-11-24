/** Altitude bands shared by the map layer and the legend (docs/08-frontend.md#visual-spec). */
export const ALTITUDE_BANDS = [
  { label: 'On ground', hex: '#7d8799', rgb: [125, 135, 153] },
  { label: '< 3,000 m', hex: '#fff1a8', rgb: [255, 241, 168] },
  { label: '3,000–7,000 m', hex: '#f2b84b', rgb: [242, 184, 75] },
  { label: '7,000–10,000 m', hex: '#e0703a', rgb: [224, 112, 58] },
  { label: '> 10,000 m', hex: '#c0447a', rgb: [192, 68, 122] },
] as const

/** RGBA for deck.gl. Stale positions (`pos_age_s > 60`) are drawn at 50% opacity. */
export function altitudeColor(
  altM: number | null,
  onGround: boolean | null,
  posAgeS: number | null,
): [number, number, number, number] {
  const alpha = posAgeS !== null && posAgeS > 60 ? 128 : 255
  if (onGround || altM === null) {
    return [ALTITUDE_BANDS[0].rgb[0], ALTITUDE_BANDS[0].rgb[1], ALTITUDE_BANDS[0].rgb[2], alpha]
  }
  const band =
    altM < 3000
      ? ALTITUDE_BANDS[1]
      : altM < 7000
        ? ALTITUDE_BANDS[2]
        : altM <= 10000
          ? ALTITUDE_BANDS[3]
          : ALTITUDE_BANDS[4]
  return [band.rgb[0], band.rgb[1], band.rgb[2], alpha]
}
