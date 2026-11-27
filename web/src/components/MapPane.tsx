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
import { useAircraftTrack, useLiveSnapshot } from '../api/queries'
import { MAP_STYLE } from '../lib/basemap'
import { parseAircraft, type Aircraft } from '../lib/aircraft'
import type { MapFocus } from '../lib/mapFocus'
import { aircraftLayer } from '../map/aircraftLayer'
import { advanceMotion, updateMotion, type MotionAircraft } from '../map/motion'
import { buildTrail, selectedHaloLayer, trailLayer, type TrailSegment } from '../map/trailLayer'
import { AircraftCard } from './AircraftCard'
import { AltitudeLegend } from './AltitudeLegend'

interface MapPaneProps {
  focus?: MapFocus | null
}

export default function MapPane({ focus = null }: MapPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<MapboxOverlay | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const motionRef = useRef<MotionAircraft[]>([])
  const trailRef = useRef<TrailSegment[]>([])
  const selectedIdRef = useRef<string | null>(null)
  const focusRef = useRef<MapFocus | null>(focus)
  const revisionRef = useRef(0)
  const rafRef = useRef<number | null>(null)
  const lastFrameRef = useRef(0)
  const lastSnapshotRef = useRef<string | null>(null)
  const { data } = useLiveSnapshot()
  const [selected, setSelected] = useState<Aircraft | null>(null)
  const track = useAircraftTrack(selected?.icao24 ?? null)

  const aircraft = useMemo(() => (data ? parseAircraft(data) : []), [data])
  const liveSelected = selected
    ? (aircraft.find((row) => row.icao24 === selected.icao24) ?? selected)
    : null

  const applyAircraft = useCallback(() => {
    const overlay = overlayRef.current
    if (!overlay) return
    revisionRef.current += 1
    const selectedMotion = selectedIdRef.current
      ? (motionRef.current.find((row) => row.icao24 === selectedIdRef.current) ?? null)
      : null
    const layers = []
    if (trailRef.current.length > 0) layers.push(trailLayer(trailRef.current))
    layers.push(selectedHaloLayer(selectedMotion))
    layers.push(
      aircraftLayer(
        motionRef.current,
        (icao24) => {
          const map = mapRef.current
          if (map) map.getCanvasContainer().style.cursor = icao24 ? 'pointer' : ''
        },
        revisionRef.current,
      ),
    )
    overlay.setProps({ layers })
  }, [])

  useEffect(() => {
    selectedIdRef.current = selected?.icao24 ?? null
    if (!selected) trailRef.current = []
    applyAircraft()
  }, [selected, applyAircraft])

  useEffect(() => {
    trailRef.current = buildTrail(track.data?.points ?? [])
    applyAircraft()
  }, [track.data, applyAircraft])

  const flyTo = useCallback((target: MapFocus) => {
    const map = mapRef.current
    if (!map) return
    map.flyTo({
      center: [target.lon, target.lat],
      zoom: Math.max(map.getZoom(), 8),
      duration: 1200,
      essential: true,
    })
  }, [])

  useEffect(() => {
    focusRef.current = focus
    if (focus) flyTo(focus)
  }, [focus, flyTo])

  // Merge each snapshot into the interpolation state, then let the animation loop
  // advance it. A repeated snapshot_time (SSE open/refetch) is ignored.
  useEffect(() => {
    if (!data) return
    const snapshotTime = data.snapshot_time
    if (snapshotTime === lastSnapshotRef.current) return
    lastSnapshotRef.current = snapshotTime
    const snapshotTimeMs = Date.parse(snapshotTime)
    motionRef.current = updateMotion(motionRef.current, aircraft, snapshotTimeMs, performance.now())
    applyAircraft()
  }, [aircraft, data, applyAircraft])

  useEffect(() => {
    const loop = (time: number) => {
      rafRef.current = requestAnimationFrame(loop)
      if (time - lastFrameRef.current < 1000 / 60) return
      lastFrameRef.current = time
      motionRef.current = advanceMotion(motionRef.current, time)
      applyAircraft()
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [applyAircraft])

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
    mapRef.current = map
    if (focusRef.current) flyTo(focusRef.current)

    const overlay = new MapboxOverlay({
      interleaved: false,
      useDevicePixels: pixelRatio,
      layers: [],
    })
    map.addControl(overlay as unknown as IControl)
    overlayRef.current = overlay
    applyAircraft()

    const onClick = (event: MapMouseEvent) => {
      const picked = overlay.pickObject({
        x: event.point.x,
        y: event.point.y,
        radius: 10,
        layerIds: ['aircraft'],
      })
      setSelected((picked?.object as Aircraft | undefined) ?? null)
    }

    map.on('click', onClick)

    return () => {
      map.off('click', onClick)
      map.getCanvasContainer().style.cursor = ''
      mapRef.current = null
      overlayRef.current = null
      map.remove()
    }
  }, [applyAircraft, flyTo])

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
