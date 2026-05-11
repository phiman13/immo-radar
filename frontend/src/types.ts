export interface Listing {
  id: number
  source_id: string
  source: string
  title: string
  price_eur: number | null
  qm: number | null
  rooms: number | null
  year_built: number | null
  property_type: string | null
  address: string | null
  city: string | null
  ortsteil: string | null
  plz: string | null
  lat: number | null
  lon: number | null
  hausgeld_eur: number | null
  energie_kwh: number | null
  energie_class: string | null
  images: string[]
  url: string
  lage_score: number | null
  ai_score: number | null
  ai_reasoning: string | null
  risk_flags: string[]
  status: string
  notes: string | null
  first_seen_at: string
  last_seen_at: string
  is_active: boolean
  enrich_attempts: number
  price_per_sqm: number | null
}

export interface Source {
  id: number
  name: string
  display_name: string
  enabled: boolean
  last_run: string | null
  listing_count: number
}

export interface AppSettings {
  poll_interval_minutes: number
  detail_fetch_interval_minutes: number
  search_radius_km: number
  price_min: number
  price_max: number
  qm_min: number
  qm_max: number
  rooms_min: number
  year_built_min: number
  property_types: string
  score_threshold: number
}

export interface JobInfo {
  id: string
  next_run: string | null
}

export interface SystemStatus {
  scheduler_running: boolean
  jobs: JobInfo[]
  listing_counts: Record<string, number>
}

export interface FetchRun {
  id: number
  source: string
  started_at: string
  finished_at: string | null
  listings_found: number
  listings_new: number
  error: string | null
}

export interface ListingsFilter {
  status: string
  source: string
  min_score: number | null
}

export type ViewMode = 'grid'

export type ListingStatus = 'new' | 'interessant' | 'vielleicht' | 'gesehen' | 'abgelehnt'

export const STATUS_LABELS: Record<string, string> = {
  new: 'Neu',
  interessant: 'Interessant',
  vielleicht: 'Vielleicht',
  gesehen: 'Gesehen',
  abgelehnt: 'Abgelehnt',
}
