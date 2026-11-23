export function Footer() {
  return (
    <footer className="flex h-9 shrink-0 items-center justify-between gap-3 border-t border-border bg-panel px-3 text-[10px] text-muted sm:px-4 sm:text-[11px]">
      <p className="truncate">
        Data:{' '}
        <a
          className="hover:text-text hover:underline"
          href="https://opensky-network.org"
          target="_blank"
          rel="noreferrer"
        >
          The OpenSky Network
        </a>{' '}
        · Map ©{' '}
        <a
          className="hover:text-text hover:underline"
          href="https://carto.com/attributions"
          target="_blank"
          rel="noreferrer"
        >
          CARTO
        </a>{' '}
        ©{' '}
        <a
          className="hover:text-text hover:underline"
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
        >
          OpenStreetMap
        </a>
      </p>
      <p className="hidden shrink-0 sm:block">Non-commercial use only</p>
    </footer>
  )
}
