import { ArrowsDownUp, Funnel } from '@phosphor-icons/react'
import { useUIStore } from '../../store/ui'
import { Source } from '../../types'
import { cn } from '../../lib/cn'

const STATUS_OPTIONS = [
  { value: '', label: 'Alle' },
  { value: 'neu', label: 'Neu' },
  { value: 'interessant', label: 'Interessant' },
  { value: 'vielleicht', label: 'Vielleicht' },
  { value: 'gesehen', label: 'Gesehen' },
  { value: 'abgelehnt', label: 'Abgelehnt' },
]

const SORT_OPTIONS = [
  { value: 'date_desc', label: 'Neueste zuerst' },
  { value: 'price_asc', label: 'Preis ↑' },
  { value: 'price_desc', label: 'Preis ↓' },
  { value: 'score_desc', label: 'Score ↓' },
  { value: 'ppm_asc', label: '€/m² ↑' },
  { value: 'ppm_desc', label: '€/m² ↓' },
]

const SCORE_OPTIONS = [
  { value: 0, label: 'Alle Scores' },
  { value: 50, label: 'Score ≥ 50' },
  { value: 70, label: 'Score ≥ 70' },
  { value: 80, label: 'Score ≥ 80' },
]

const ROOMS_OPTIONS = [
  { value: '', label: 'Zi. egal' },
  { value: '2', label: '2+' },
  { value: '3', label: '3+' },
  { value: '4', label: '4+' },
  { value: '5', label: '5+' },
]

interface Props { sources: Source[] }

export function FilterBar({ sources }: Props) {
  const { filter, setFilter } = useUIStore()

  const hasActiveFilters = !!(
    filter.priceMin || filter.priceMax || filter.qmMin || filter.qmMax ||
    filter.roomsMin || filter.status || filter.portal || filter.minScore
  )

  return (
    <div className="sticky top-0 z-20 bg-[--bg] border-b border-[--border] px-6 py-3 space-y-2">
      {/* Row 1: Status chips + Sort */}
      <div className="flex items-center gap-2 flex-wrap">
        {STATUS_OPTIONS.map(opt => (
          <button
            key={opt.value}
            onClick={() => setFilter({ status: opt.value })}
            className={cn(
              'px-3 py-1 rounded-full text-sm font-medium border transition-colors',
              filter.status === opt.value
                ? 'bg-[--accent] text-white border-[--accent]'
                : 'border-[--border] text-[--muted] hover:border-[--accent] hover:text-[--accent]'
            )}
          >
            {opt.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-1.5 text-[--muted]">
          <ArrowsDownUp size={14} weight="bold" />
          <select
            value={filter.sort}
            onChange={e => setFilter({ sort: e.target.value as typeof filter.sort })}
            className="text-sm bg-transparent border-none outline-none text-[--fg] cursor-pointer"
          >
            {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      </div>

      {/* Row 2: Numeric filters */}
      <div className="flex items-center gap-3 flex-wrap text-sm">
        {/* Price range */}
        <div className="flex items-center gap-1">
          <span className="text-[--muted] text-xs">€</span>
          <input
            type="number" placeholder="Min" step={50000}
            value={filter.priceMin ?? ''}
            onChange={e => setFilter({ priceMin: e.target.value ? Number(e.target.value) : null })}
            className="w-24 px-2 py-1 rounded border border-[--border] bg-white font-mono text-xs focus:outline-none focus:border-[--accent]"
          />
          <span className="text-[--muted]">–</span>
          <input
            type="number" placeholder="Max" step={50000}
            value={filter.priceMax ?? ''}
            onChange={e => setFilter({ priceMax: e.target.value ? Number(e.target.value) : null })}
            className="w-24 px-2 py-1 rounded border border-[--border] bg-white font-mono text-xs focus:outline-none focus:border-[--accent]"
          />
        </div>

        <div className="w-px h-4 bg-[--border]" />

        {/* m² range */}
        <div className="flex items-center gap-1">
          <span className="text-[--muted] text-xs">m²</span>
          <input
            type="number" placeholder="Min"
            value={filter.qmMin ?? ''}
            onChange={e => setFilter({ qmMin: e.target.value ? Number(e.target.value) : null })}
            className="w-16 px-2 py-1 rounded border border-[--border] bg-white font-mono text-xs focus:outline-none focus:border-[--accent]"
          />
          <span className="text-[--muted]">–</span>
          <input
            type="number" placeholder="Max"
            value={filter.qmMax ?? ''}
            onChange={e => setFilter({ qmMax: e.target.value ? Number(e.target.value) : null })}
            className="w-16 px-2 py-1 rounded border border-[--border] bg-white font-mono text-xs focus:outline-none focus:border-[--accent]"
          />
        </div>

        <div className="w-px h-4 bg-[--border]" />

        {/* Rooms */}
        <select
          value={filter.roomsMin ?? ''}
          onChange={e => setFilter({ roomsMin: e.target.value ? Number(e.target.value) : null })}
          className="px-2 py-1 rounded border border-[--border] bg-white text-xs focus:outline-none focus:border-[--accent] text-[--fg]"
        >
          {ROOMS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        {/* Score */}
        <select
          value={filter.minScore}
          onChange={e => setFilter({ minScore: Number(e.target.value) })}
          className="px-2 py-1 rounded border border-[--border] bg-white text-xs focus:outline-none focus:border-[--accent] text-[--fg]"
        >
          {SCORE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        {/* Portal */}
        {sources.length > 0 && (
          <select
            value={filter.portal}
            onChange={e => setFilter({ portal: e.target.value })}
            className="px-2 py-1 rounded border border-[--border] bg-white text-xs focus:outline-none focus:border-[--accent] text-[--fg]"
          >
            <option value="">Alle Portale</option>
            {sources.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
          </select>
        )}

        {/* Reset */}
        {hasActiveFilters && (
          <button
            onClick={() => setFilter({
              priceMin: null, priceMax: null, qmMin: null, qmMax: null,
              roomsMin: null, status: '', portal: '', minScore: 0
            })}
            className="ml-auto text-xs text-[--muted] hover:text-[--accent] flex items-center gap-1"
          >
            <Funnel size={12} /> Filter löschen
          </button>
        )}
      </div>
    </div>
  )
}
