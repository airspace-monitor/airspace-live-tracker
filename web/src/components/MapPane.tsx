import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  type IControl,
  type MapMouseEvent,
} from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import 'maplibre-gl/dist/maplibre-gl.css'
import './map.css'
import { useLiveSnapshot } from '../api/queries'
import { MAP_STYLE } from '../lib/basemap'
import { parseAircraft, type Aircraft } from '../lib/aircraft'
import { aircraftLayer } from '../map/aircraftLayer'
import { AircraftCard } from './AircraftCard'
import { AltitudeLegend } from './AltitudeLegend'

export default function MapPane() {
  const containerRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<MapboxOverlay | null>(null)
  const aircraftRef = useRef<Aircraft[]>([])
  const hoveredRef = useRef<string | null>(null)
  const { data } = useLiveSnapshot()
  const [selected, setSelected] = useState<Aircraft | null>(null)

  const aircraft = useMemo(() => (data ? parseAircraft(data) : []), [data])
  const liveSelected = selected
    ? (aircraft.find((row) => row.icao24 === selected.icao24) ?? selected)
    : null

  const applyAircraft = useCallback(() => {
    const overlay = overlayRef.current
    if (!overlay) return
    overlay.setProps({ layers: [aircraftLayer(aircraftRef.current, hoveredRef.current)] })
  }, [])

  // The query usually resolves after the map effect. Keep the latest rows in a ref and
  // apply them whenever either side becomes ready.
  useEffect(() => {
    aircraftRef.current = aircraft
    applyAircraft()
  }, [aircraft, applyAircraft])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelected(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // Cap the backing store: 2x-3x displays spend 2-4x the fragments for little map detail.
    const pixelRatio = Math.min(window.devicePixelRatio, 1.5)

    const map = new MapLibreMap({
      container,
      style: MAP_STYLE,
      center: [16.37, 48.21],
      zoom: 4.2,
      attributionControl: false,
      pixelRatio,
      fadeDuration: 0,
      renderWorldCopies: false,
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')

    const overlay = new MapboxOverlay({
      interleaved: false,
      useDevicePixels: pixelRatio,
      layers: [],
    })
    map.addControl(overlay as unknown as IControl)
    overlayRef.current = overlay
    applyAircraft()

    // Hover is picked only after the pointer pauses briefly. This keeps the
    // accent colour without deck.gl picking over 12k icons on every move.
    let hoverTimer: number | null = null
    let hoverPoint: { x: number; y: number } | null = null

    const clearHover = () => {
      if (hoverTimer !== null) {
        window.clearTimeout(hoverTimer)
        hoverTimer = null
      }
      hoverPoint = null
      if (hoveredRef.current !== null) {
        hoveredRef.current = null
        applyAircraft()
        map.getCanvasContainer().style.cursor = ''
      }
    }

    const onMouseMove = (event: MapMouseEvent) => {
      if (map.isMoving()) return
      hoverPoint = { x: event.point.x, y: event.point.y }
      if (hoverTimer !== null) window.clearTimeout(hoverTimer)
      hoverTimer = window.setTimeout(() => {
        hoverTimer = null
        if (!hoverPoint) return
        const picked = overlay.pickObject({
          x: hoverPoint.x,
          y: hoverPoint.y,
          radius: 10,
          layerIds: ['aircraft'],
        })
        const icao24 = (picked?.object as Aircraft | undefined)?.icao24 ?? null
        if (icao24 === hoveredRef.current) return
        hoveredRef.current = icao24
        applyAircraft()
        map.getCanvasContainer().style.cursor = icao24 ? 'pointer' : ''
      }, 70)
    }

    const onClick = (event: MapMouseEvent) => {
      const picked = overlay.pickObject({
        x: event.point.x,
        y: event.point.y,
        radius: 10,
        layerIds: ['aircraft'],
      })
      setSelected((picked?.object as Aircraft | undefined) ?? null)
    }

    map.on('mousemove', onMouseMove)
    map.on('mouseout', clearHover)
    map.on('movestart', clearHover)
    map.on('click', onClick)

    return () => {
      clearHover()
      map.off('mousemove', onMouseMove)
      map.off('mouseout', clearHover)
      map.off('movestart', clearHover)
      map.off('click', onClick)
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

      {liveSelected ? (
        <AircraftCard aircraft={liveSelected} onClose={() => setSelected(null)} />
      ) : null}

      <AltitudeLegend />
    </div>
  )
}
