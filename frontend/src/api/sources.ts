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
