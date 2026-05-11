import { X } from '@phosphor-icons/react'
import { useUIStore } from '../../store/ui'
import { STATUS_LABELS } from '../../types'
import { cn } from '../../lib/cn'

const STATUS_OPTIONS = [
  { value: '', label: 'Alle' },
  { value: 'new', label: STATUS_LABELS.new },
  { value: 'interessant', label: STATUS_LABELS.interessant },
  { value: 'vielleicht', label: STATUS_LABELS.vielleicht },
  { value: 'gesehen', label: STATUS_LABELS.gesehen },
  { value: 'abgelehnt', label: STATUS_LABELS.abgelehnt },
]

const SCORE_OPTIONS = [
  { value: null, label: 'Alle Scores' },
  { value: 50, label: 'Score ≥ 50' },
  { value: 70, label: 'Score ≥ 70' },
  { value: 80, label: 'Score ≥ 80' },
]

interface FilterBarProps {
  sources: string[]
  totalCount: number
}

export function FilterBar({ sources, totalCount }: FilterBarProps) {
  const { filter, setFilter, resetFilter } = useUIStore()
  const hasActiveFilter = filter.status !== '' || filter.source !== '' || filter.min_score != null

  return (
    <div
      className="sticky top-0 z-10 border-b px-6 py-3 flex items-center gap-3 flex-wrap"
      style={{ background: 'var(--bg)', borderColor: 'var(--border)' }}
    >
      {/* Status chips */}
      <div className="flex items-center gap-1">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter({ status: opt.value })}
            className={cn(
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              filter.status === opt.value
                ? 'text-white'
                : 'hover:bg-[var(--accent-muted)]',
            )}
            style={
              filter.status === opt.value
                ? { background: 'var(--accent)', color: 'white' }
                : { color: 'var(--fg)' }
            }
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="h-4 w-px" style={{ background: 'var(--border)' }} />

      {/* Score filter */}
      <select
        value={filter.min_score ?? ''}
        onChange={(e) =>
          setFilter({ min_score: e.target.value === '' ? null : Number(e.target.value) })
        }
        className="text-xs px-2 py-1 rounded-lg border bg-white"
        style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
      >
        {SCORE_OPTIONS.map((opt) => (
          <option key={String(opt.value)} value={opt.value ?? ''}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Source filter */}
      {sources.length > 1 && (
        <select
          value={filter.source}
          onChange={(e) => setFilter({ source: e.target.value })}
          className="text-xs px-2 py-1 rounded-lg border bg-white"
          style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
        >
          <option value="">Alle Quellen</option>
          {sources.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      )}

      {/* Reset */}
      {hasActiveFilter && (
        <button
          onClick={resetFilter}
          className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg transition-colors hover:bg-[var(--accent-muted)]"
          style={{ color: 'var(--muted)' }}
        >
          <X size={12} />
          Filter zurücksetzen
        </button>
      )}

      {/* Count */}
      <span className="ml-auto text-xs" style={{ color: 'var(--muted)' }}>
        {totalCount} {totalCount === 1 ? 'Objekt' : 'Objekte'}
      </span>
    </div>
  )
}
