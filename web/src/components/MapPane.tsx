import { useCallback, useEffect, useMemo, useRef } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  type IControl,
  type StyleSpecification,
} from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useLiveSnapshot } from '../api/queries'
import { parseAircraft, type Aircraft } from '../lib/aircraft'
import { aircraftLayer } from '../map/aircraftLayer'
import { AltitudeLegend } from './AltitudeLegend'

const STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#0b1020' },
    },
  ],
}

export default function MapPane() {
  const containerRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<MapboxOverlay | null>(null)
  const aircraftRef = useRef<Aircraft[]>([])
  const { data } = useLiveSnapshot()

  const aircraft = useMemo(() => (data ? parseAircraft(data) : []), [data])

  const applyAircraft = useCallback(() => {
    const overlay = overlayRef.current
    if (!overlay) return
    overlay.setProps({ layers: [aircraftLayer(aircraftRef.current)] })
  }, [])

  // The query usually resolves after the map effect. Keep the latest rows in a ref and
  // apply them whenever either side becomes ready.
  useEffect(() => {
    aircraftRef.current = aircraft
    applyAircraft()
  }, [aircraft, applyAircraft])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const map = new MapLibreMap({
      container,
      style: STYLE,
      center: [16.37, 48.21],
      zoom: 4.2,
      attributionControl: false,
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')

    const overlay = new MapboxOverlay({ interleaved: false, layers: [] })
    map.addControl(overlay as unknown as IControl)
    overlayRef.current = overlay
    applyAircraft()

    return () => {
      overlayRef.current = null
      map.remove()
    }
  }, [applyAircraft])

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      <div className="pointer-events-none absolute left-3 top-3 z-20 rounded border border-border bg-panel px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted">
        Europe · zoom 4
      </div>

      <AltitudeLegend />
    </div>
  )
}
