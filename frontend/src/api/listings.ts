import { api } from './client'
import type { Listing } from '../types'

export interface ListingsQuery {
  status?: string
  portal?: string
  min_score?: number
}

export function fetchListings(query: ListingsQuery = {}): Promise<Listing[]> {
  const params = new URLSearchParams()
  if (query.status) params.set('status', query.status)
  if (query.portal) params.set('portal', query.portal)
  if (query.min_score != null) params.set('min_score', String(query.min_score))
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
