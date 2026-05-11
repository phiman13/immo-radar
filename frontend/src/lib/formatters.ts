export function formatPrice(eur: number | null): string {
  if (eur == null) return '–'
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(eur)
}

export function formatPricePerSqm(ppsm: number | null): string {
  if (ppsm == null) return '–'
  return new Intl.NumberFormat('de-DE', {
    maximumFractionDigits: 0,
  }).format(ppsm) + ' €/m²'
}

export function formatSqm(qm: number | null): string {
  if (qm == null) return '–'
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 }).format(qm) + ' m²'
}

export function formatRooms(rooms: number | null): string {
  if (rooms == null) return '–'
  return rooms % 1 === 0 ? `${rooms} Zi.` : `${rooms} Zi.`
}

export function formatDaysOnMarket(firstSeenAt: string): string {
  const days = Math.floor(
    (Date.now() - new Date(firstSeenAt).getTime()) / 86_400_000,
  )
  if (days === 0) return 'heute'
  if (days === 1) return 'seit gestern'
  return `seit ${days} Tagen`
}

export function formatTimeAgo(isoDate: string): string {
  const mins = Math.floor((Date.now() - new Date(isoDate).getTime()) / 60_000)
  if (mins < 1) return 'gerade eben'
  if (mins < 60) return `vor ${mins} Min.`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `vor ${hours} Std.`
  const days = Math.floor(hours / 24)
  return `vor ${days} Tagen`
}
