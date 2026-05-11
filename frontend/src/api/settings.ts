import { api } from './client'
import type { AppSettings } from '../types'

export function fetchSettings(): Promise<{ settings: AppSettings }> {
  return api.get('/api/settings/')
}

export function patchSetting(key: string, value: unknown): Promise<{ settings: AppSettings }> {
  return api.patch('/api/settings/', { key, value })
}
