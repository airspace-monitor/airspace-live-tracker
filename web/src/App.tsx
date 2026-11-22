import { lazy, Suspense, useState } from 'react'
import { BottomSheet } from './components/BottomSheet'
import { Footer } from './components/Footer'
import { Header } from './components/Header'
import { SidePanel } from './components/SidePanel'
import { useLiveStream } from './hooks/useLiveStream'
import { useMediaQuery } from './hooks/useMediaQuery'
import { DEFAULT_TAB, type TabId } from './lib/panels'

// Lazy boundary: MapLibre/deck.gl must stay out of the shell bundle (M2.5).
const MapPane = lazy(() => import('./components/MapPane'))

function MapFallback() {
  return <div className="h-full w-full animate-pulse bg-land" aria-label="Loading map" />
}

export default function App() {
  const [tab, setTab] = useState<TabId>(DEFAULT_TAB)
  const desktop = useMediaQuery('(min-width: 900px)')
  useLiveStream()

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-bg text-text">
      <Header />

      <main
        className={
          desktop
            ? 'grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_380px]'
            : 'relative min-h-0 flex-1'
        }
      >
        <div className="relative h-full min-h-0">
          <Suspense fallback={<MapFallback />}>
            <MapPane />
          </Suspense>
        </div>

        {desktop ? (
          <SidePanel active={tab} onChange={setTab} />
        ) : (
          <BottomSheet active={tab} onChange={setTab} />
        )}
      </main>

      <Footer />
    </div>
  )
}
