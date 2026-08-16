import { useEffect, useRef } from 'react'
import L from 'leaflet'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

interface Props {
  lat: number
  lon: number
  zoom?: number
  height?: string
}

export function ListingMiniMap({ lat, lon, zoom = 14, height = '160px' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    // Fix default marker icons broken in Vite. HER-818: vorher von
    // unpkg.com geladen (externe CDN-Abhängigkeit) -- jetzt aus dem
    // installierten leaflet-Paket gebündelt.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (L.Icon.Default.prototype as any)._getIconUrl
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: markerIcon2x,
      iconUrl: markerIcon,
      shadowUrl: markerShadow,
    })

    const map = L.map(containerRef.current, {
      center: [lat, lon],
      zoom,
      scrollWheelZoom: false,
      dragging: false,
      zoomControl: false,
      attributionControl: true,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map)

    L.marker([lat, lon]).addTo(map)
    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [lat, lon, zoom])

  return (
    <div
      ref={containerRef}
      className="rounded-lg overflow-hidden border border-[--border]"
      style={{ height }}
    />
  )
}
