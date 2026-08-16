import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { useDebounce } from '../../hooks/useDebounce'

export interface SearchLocation {
  lat: number
  lon: number
  radius_km: number
  label: string
}

interface Props {
  locations: SearchLocation[]
  onChange: (locations: SearchLocation[]) => void
}

const CIRCLE_COLORS = [
  'var(--accent)',
  '#f59e0b',
  '#10b981',
  '#8b5cf6',
  '#ef4444',
]

export function MultiLocationPicker({ locations, onChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<L.Marker[]>([])
  const circlesRef = useRef<L.Circle[]>([])
  const locationsRef = useRef<SearchLocation[]>(locations)

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 1000)

  // Keep ref in sync for drag handlers (avoid stale closures)
  useEffect(() => {
    locationsRef.current = locations
  }, [locations])

  // Init map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    // Fix Vite marker icons: Leaflet's default _getIconUrl assumes a
    // classic (non-bundled) asset layout. HER-818: vorher von unpkg.com
    // geladen (externe CDN-Abhängigkeit) -- jetzt aus dem bereits
    // installierten leaflet-Paket gebündelt, kein Netzwerk-Roundtrip zu
    // einem Drittanbieter mehr nötig.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (L.Icon.Default.prototype as any)._getIconUrl
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: markerIcon2x,
      iconUrl: markerIcon,
      shadowUrl: markerShadow,
    })

    const initialCenter: L.LatLngExpression = locations.length > 0
      ? [locations[0].lat, locations[0].lon]
      : [47.9095, 11.2783]

    const map = L.map(containerRef.current, {
      center: initialCenter,
      zoom: 10,
      scrollWheelZoom: true,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map)

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      markersRef.current = []
      circlesRef.current = []
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Sync markers/circles when locations change
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    // Remove all old markers and circles
    markersRef.current.forEach(m => m.remove())
    circlesRef.current.forEach(c => c.remove())
    markersRef.current = []
    circlesRef.current = []

    // Add new markers and circles for each location
    locations.forEach((loc, i) => {
      const color = CIRCLE_COLORS[i % CIRCLE_COLORS.length]
      const marker = L.marker([loc.lat, loc.lon], { draggable: true }).addTo(map)
      const circle = L.circle([loc.lat, loc.lon], {
        radius: loc.radius_km * 1000,
        color,
        fillColor: color,
        fillOpacity: 0.08,
        weight: 2,
      }).addTo(map)

      marker.on('dragend', () => {
        const pos = marker.getLatLng()
        circle.setLatLng(pos)
        const updated = [...locationsRef.current]
        updated[i] = { ...updated[i], lat: pos.lat, lon: pos.lng }
        onChange(updated)
      })

      markersRef.current.push(marker)
      circlesRef.current.push(circle)
    })
  }, [locations]) // eslint-disable-line react-hooks/exhaustive-deps

  // Geocode search via Nominatim
  useEffect(() => {
    if (!debouncedSearch || debouncedSearch.length < 3 || !mapRef.current) return

    fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(debouncedSearch)}&format=json&limit=1&countrycodes=de`,
      { headers: { 'Accept-Language': 'de', 'User-Agent': 'immo-radar/1.0 philipp.herrlich@googlemail.com' } }
    )
      .then(r => r.json())
      .then((results: Array<{ lat: string; lon: string; display_name: string }>) => {
        if (!results[0]) return
        const lat = parseFloat(results[0].lat)
        const lon = parseFloat(results[0].lon)
        mapRef.current?.setView([lat, lon], 12)
        onChange([...locationsRef.current, { lat, lon, radius_km: 5, label: debouncedSearch }])
        setSearch('')
      })
      .catch(() => {})
  }, [debouncedSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  function addAtCenter() {
    const center = mapRef.current?.getCenter() ?? { lat: 47.9095, lng: 11.2783 }
    onChange([...locations, { lat: center.lat, lon: center.lng, radius_km: 5, label: '' }])
  }

  function remove(i: number) {
    if (locations.length <= 1) return // min 1 location
    onChange(locations.filter((_, idx) => idx !== i))
  }

  function updateLabel(i: number, label: string) {
    const updated = [...locations]
    updated[i] = { ...updated[i], label }
    onChange(updated)
  }

  function updateRadius(i: number, radius_km: number) {
    const updated = [...locations]
    updated[i] = { ...updated[i], radius_km }
    circlesRef.current[i]?.setRadius(radius_km * 1000)
    onChange(updated)
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Ort suchen + hinzufügen (z.B. Starnberg…)"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 px-3 py-2 rounded-lg border text-sm focus:outline-none"
          style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
          onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
          onBlur={e => (e.target.style.borderColor = 'var(--border)')}
        />
        <button
          onClick={addAtCenter}
          className="px-3 py-2 rounded-lg border text-sm"
          style={{ borderColor: 'var(--border)', color: 'var(--muted)' }}
          title="Kartenmittelpunkt als Standort hinzufügen"
        >
          + Ort
        </button>
      </div>

      <div
        ref={containerRef}
        className="rounded-lg overflow-hidden border"
        style={{ height: '280px', borderColor: 'var(--border)' }}
      />

      <div className="space-y-2">
        {locations.map((loc, i) => (
          <div
            key={i}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border"
            style={{
              borderColor: 'var(--border)',
              borderLeftColor: CIRCLE_COLORS[i % CIRCLE_COLORS.length],
              borderLeftWidth: '3px',
            }}
          >
            <input
              type="text"
              placeholder={`Standort ${i + 1}`}
              value={loc.label}
              onChange={e => updateLabel(i, e.target.value)}
              className="flex-1 text-sm px-2 py-1 rounded border focus:outline-none"
              style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
            />
            <input
              type="range"
              min={1}
              max={25}
              step={1}
              value={loc.radius_km}
              onChange={e => updateRadius(i, Number(e.target.value))}
              className="w-20 accent-[var(--accent)]"
            />
            <span className="font-mono text-xs w-10 text-right" style={{ color: 'var(--muted)' }}>
              {loc.radius_km} km
            </span>
            <button
              onClick={() => remove(i)}
              disabled={locations.length <= 1}
              className="text-xs px-1.5 py-1 rounded disabled:opacity-30"
              style={{ color: 'var(--muted)' }}
              title="Standort entfernen"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
