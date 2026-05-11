import { api } from './client'
import type { Source } from '../types'

export function fetchSources(): Promise<Source[]> {
  return api.get('/api/sources/')
}

export function patchSource(
  id: number,
  body: { enabled?: boolean; display_name?: string },
): Promise<Source> {
  return api.patch(`/api/sources/${id}`, body)
}

export interface AnalyzeResult {
  url: string
  listing_count: number
  example_title: string | null
  example_price: string | null
  fields: { price: boolean; qm: boolean; rooms: boolean; address: boolean; images: boolean }
  error: string | null
}

export interface DiscoverSuggestion {
  name: string
  url: string
  description: string
}

export async function analyzeSource(url: string): Promise<AnalyzeResult> {
  const res = await api.post<AnalyzeResult>('/api/sources/analyze', { url })
  return res.data
}

export async function discoverSources(): Promise<DiscoverSuggestion[]> {
  const res = await api.post<{ suggestions: DiscoverSuggestion[]; error: string | null }>('/api/sources/discover')
  if (res.data.error) throw new Error(res.data.error)
  return res.data.suggestions
}

export async function createSource(body: {
  name: string
  display_name: string
  url?: string
  source_type?: string
}): Promise<Source> {
  const res = await api.post<Source>('/api/sources/', body)
  return res.data
}
