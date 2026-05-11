import { api } from './client'
import type { AppSettings } from '../types'

type RawSettings = Omit<AppSettings, 'property_types'> & { property_types: string }

function parseSettings(raw: RawSettings): AppSettings {
  return {
    ...raw,
    property_types: raw.property_types
      ? raw.property_types.split(',').map((s) => s.trim()).filter(Boolean)
      : [],
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
