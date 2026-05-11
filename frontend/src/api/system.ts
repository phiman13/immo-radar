import { api } from './client'
import type { SystemStatus, FetchRun } from '../types'

export function fetchSystemStatus(): Promise<SystemStatus> {
  return api.get('/api/system/status')
}

export function fetchFetchRuns(): Promise<FetchRun[]> {
  return api.get('/api/system/fetch-runs')
}

export function triggerCrawl(): Promise<{ status: string }> {
  return api.post('/api/system/crawl/trigger')
}
