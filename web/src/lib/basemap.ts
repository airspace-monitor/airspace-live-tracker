/**
 * Basemap selection. The CARTO key lives only in `web/.env` (git-ignored) or the
 * Pages environment; it is never committed. Without a key the app falls back to
 * OpenFreeMap Dark so local development works offline from CARTO credentials.
 */
const CARTO_KEY = import.meta.env.VITE_CARTO_KEY as string | undefined
const STYLE_OVERRIDE = import.meta.env.VITE_MAP_STYLE_URL as string | undefined

const CARTO_DARK_MATTER = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const OPENFREEMAP_DARK = 'https://tiles.openfreemap.org/styles/dark'

export const USING_CARTO = STYLE_OVERRIDE ? STYLE_OVERRIDE.includes('cartocdn') : Boolean(CARTO_KEY)

export const MAP_STYLE =
  STYLE_OVERRIDE ||
  (CARTO_KEY ? `${CARTO_DARK_MATTER}?key=${encodeURIComponent(CARTO_KEY)}` : OPENFREEMAP_DARK)
