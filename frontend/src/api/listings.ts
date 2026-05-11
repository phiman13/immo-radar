import { api } from './client'
import type { Listing } from '../types'

export interface ListingsQuery {
  status?: string
  portal?: string
  min_score?: number
  price_min?: number | null
  price_max?: number | null
  qm_min?: number | null
  qm_max?: number | null
  rooms_min?: number | null
  sort?: string
}

export function fetchListings(query: ListingsQuery = {}): Promise<Listing[]> {
  const params = new URLSearchParams()
  if (query.status) params.set('status', query.status)
  if (query.portal) params.set('portal', query.portal)
  if (query.min_score != null) params.set('min_score', String(query.min_score))
  if (query.price_min != null) params.set('price_min', String(query.price_min))
  if (query.price_max != null) params.set('price_max', String(query.price_max))
  if (query.qm_min != null) params.set('qm_min', String(query.qm_min))
  if (query.qm_max != null) params.set('qm_max', String(query.qm_max))
  if (query.rooms_min != null) params.set('rooms_min', String(query.rooms_min))
  if (query.sort && query.sort !== 'date_desc') params.set('sort', query.sort)
  const qs = params.toString()
  return api.get<Listing[]>(`/api/listings/${qs ? '?' + qs : ''}`)
}

export function fetchListing(id: number): Promise<Listing> {
  return api.get<Listing>(`/api/listings/${id}`)
}

export function patchListing(
  id: number,
  body: { status?: string; notes?: string },
): Promise<Listing> {
  return api.patch<Listing>(`/api/listings/${id}`, body)
}
