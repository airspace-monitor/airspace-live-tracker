/**
 * A single white plane pointing north, used as the IconLayer mask atlas.
 * The layer tints it per aircraft with `getColor`; `mask: true` makes the
 * white pixels the tinted area instead of the background.
 */
const PLANE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><path fill="#ffffff" d="M32 2c2.2 0 3.5 2.4 3.5 5.8v14.3L62 38.5v6.2L35.5 36v14.2l8.6 6.1v4.3L32 58l-12.1 2.6v-4.3l8.6-6.1V36L2 44.7v-6.2l26.5-16.4V7.8C28.5 4.4 29.8 2 32 2z"/></svg>`

export const PLANE_ICON_ATLAS = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(PLANE_SVG)}`

export const PLANE_ICON_MAPPING = {
  plane: {
    x: 0,
    y: 0,
    width: 64,
    height: 64,
    anchorX: 32,
    anchorY: 32,
    mask: true,
  },
}
