import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { useDebounce } from '../../hooks/useDebounce'

interface Props {
  lat: number
  lon: number
  radiusKm: number
  onChangeCenter: (lat: number, lon: number) => void
  onChangeRadius: (km: number) => void
}

export function LocationPicker({ lat, lon, radiusKm, onChangeCenter, onChangeRadius }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markerRef = useRef<L.Marker | null>(null)
  const circleRef = useRef<L.Circle | null>(null)

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 1000)

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    // Fix default marker icons broken in Vite
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (L.Icon.Default.prototype as any)._getIconUrl
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
      iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    })

    const map = L.map(containerRef.current, {
      center: [lat, lon],
      zoom: 11,
      scrollWheelZoom: true,
      zoomControl: true,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map)

    const marker = L.marker([lat, lon], { draggable: true }).addTo(map)
    const circle = L.circle([lat, lon], {
      radius: radiusKm * 1000,
      color: 'var(--accent)',
      fillColor: 'var(--accent)',
      fillOpacity: 0.08,
      weight: 2,
    }).addTo(map)

    marker.on('dragend', () => {
      const pos = marker.getLatLng()
      circle.setLatLng(pos)
      onChangeCenter(pos.lat, pos.lng)
    })

    mapRef.current = map
    markerRef.current = marker
    circleRef.current = circle

    return () => {
      map.remove()
      mapRef.current = null
      markerRef.current = null
      circleRef.current = null
    }
  }, []) // init once — lat/lon/radiusKm captured at init time

  // Sync radius circle when prop changes
  useEffect(() => {
    circleRef.current?.setRadius(radiusKm * 1000)
  }, [radiusKm])

  // Nominatim geocode after 1s debounce
  useEffect(() => {
    if (!debouncedSearch || debouncedSearch.length < 3) return

    fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(debouncedSearch)}&format=json&limit=1&countrycodes=de`,
      {
        headers: {
          'Accept-Language': 'de',
          'User-Agent': 'immo-radar/1.0 philipp.herrlich@googlemail.com',
        },
      }
    )
      .then((r) => r.json())
      .then((results: Array<{ lat: string; lon: string }>) => {
        if (!results[0]) return
        const newLat = parseFloat(results[0].lat)
        const newLon = parseFloat(results[0].lon)
        const pos: L.LatLngExpression = [newLat, newLon]
        mapRef.current?.setView(pos, 12)
        markerRef.current?.setLatLng(pos)
        circleRef.current?.setLatLng(pos)
        onChangeCenter(newLat, newLon)
      })
      .catch(() => {
        // Nominatim rate limit or network error — silent fail, user can retry
      })
  }, [debouncedSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-2">
      <input
        type="text"
        placeholder="Ort suchen (z.B. Tutzing, Starnberg…)"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border text-sm focus:outline-none"
        style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
        onFocus={(e) => (e.target.style.borderColor = 'var(--accent)')}
        onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
      />
      <div
        ref={containerRef}
        className="rounded-lg overflow-hidden border"
        style={{ height: '280px', borderColor: 'var(--border)' }}
      />
      <div className="flex items-center gap-3 pt-1">
        <span className="text-xs" style={{ color: 'var(--muted)' }}>Radius:</span>
        <input
          type="range"
          min={1}
          max={25}
          step={1}
          defaultValue={radiusKm}
          onMouseUp={(e) => onChangeRadius(Number((e.target as HTMLInputElement).value))}
          className="flex-1 accent-[var(--accent)]"
        />
        <span className="font-mono text-sm w-12 text-right" style={{ color: 'var(--fg)' }}>
          {radiusKm} km
        </span>
      </div>
    </div>
  )
}
