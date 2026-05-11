import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { Listing } from '../../types'
import { formatPrice } from '../../lib/formatters'

const STATUS_COLORS: Record<string, string> = {
  neu: '#22c55e',
  interessant: '#22c55e',
  vielleicht: '#f59e0b',
  gesehen: '#94a3b8',
  abgelehnt: '#ef4444',
}
const DEFAULT_COLOR = '#94a3b8'

interface Props {
  listings: Listing[]
  selectedId: number | null
  onListingClick: (id: number) => void
}

export function ListingsMap({ listings, selectedId, onListingClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<L.CircleMarker[]>([])

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, {
      center: [47.905, 11.285], // Tutzing
      zoom: 12,
    })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Re-render markers when listings or selection changes
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    // Clear existing markers
    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []

    const withCoords = listings.filter((l) => l.lat != null && l.lon != null)

    withCoords.forEach((l) => {
      const isSelected = l.id === selectedId
      const marker = L.circleMarker([l.lat!, l.lon!], {
        radius: isSelected ? 12 : 8,
        fillColor: STATUS_COLORS[l.status] ?? DEFAULT_COLOR,
        color: '#ffffff',
        weight: isSelected ? 3 : 2,
        fillOpacity: 0.9,
      })
      marker.bindPopup(
        `<div style="font-family:sans-serif;min-width:160px">` +
          `<div style="font-weight:600;font-size:13px;margin-bottom:4px">${l.title}</div>` +
          `<div style="font-family:monospace;color:#555">${formatPrice(l.price_eur)}</div>` +
          `</div>`,
      )
      marker.on('click', () => onListingClick(l.id))
      marker.addTo(map)
      markersRef.current.push(marker)
    })

    // Fit bounds to all markers if we have any
    if (withCoords.length > 0) {
      const bounds = L.latLngBounds(
        withCoords.map((l) => [l.lat!, l.lon!] as [number, number]),
      )
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
    }
  }, [listings, selectedId, onListingClick])

  return <div ref={containerRef} className="w-full h-full" />
}
