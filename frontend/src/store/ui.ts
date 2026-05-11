import { create } from 'zustand'
import type { ListingsFilter } from '../types'

interface UIState {
  selectedListingId: number | null
  setSelectedListingId: (id: number | null) => void

  filter: ListingsFilter
  setFilter: (patch: Partial<ListingsFilter>) => void
  resetFilter: () => void
}

const DEFAULT_FILTER: ListingsFilter = {
  status: '',
  source: '',
  min_score: null,
  portal: '',
  minScore: 0,
  priceMin: null,
  priceMax: null,
  qmMin: null,
  qmMax: null,
  roomsMin: null,
  sort: 'date_desc' as const,
}

export const useUIStore = create<UIState>((set) => ({
  selectedListingId: null,
  setSelectedListingId: (id) => set({ selectedListingId: id }),

  filter: DEFAULT_FILTER,
  setFilter: (patch) =>
    set((s) => ({ filter: { ...s.filter, ...patch } })),
  resetFilter: () => set({ filter: DEFAULT_FILTER }),
}))
