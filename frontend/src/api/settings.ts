import { api } from './client'
import type { AppSettings, SearchLocation } from '../types'

type RawSettings = Omit<AppSettings, 'property_types' | 'search_locations'> & {
  property_types: string
  search_locations: SearchLocation[] | string | null
}

function parseSettings(raw: RawSettings): AppSettings {
  let search_locations: SearchLocation[] = []
  if (Array.isArray(raw.search_locations)) {
    search_locations = raw.search_locations
  } else if (typeof raw.search_locations === 'string' && raw.search_locations) {
    try {
      search_locations = JSON.parse(raw.search_locations)
    } catch {
      search_locations = []
    }
  }
  return {
    ...raw,
    property_types: raw.property_types
      ? raw.property_types.split(',').map((s) => s.trim()).filter(Boolean)
      : [],
    search_locations,
  }
}

export async function fetchSettings(): Promise<{ settings: AppSettings }> {
  const data = await api.get<{ settings: RawSettings }>('/api/settings/')
  return { settings: parseSettings(data.settings) }
}

export async function patchSetting(key: string, value: unknown): Promise<{ settings: AppSettings }> {
  const data = await api.patch<{ settings: RawSettings }>('/api/settings/', { key, value })
  return { settings: parseSettings(data.settings) }
}
