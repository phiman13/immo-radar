import { ArrowSquareOut, Heart, X } from '@phosphor-icons/react'
import { motion } from 'framer-motion'
import type { Listing } from '../../types'
import { StatusChip } from './StatusChip'
import { ScoreBadge } from './ScoreBadge'
import {
  formatPrice,
  formatPricePerSqm,
  formatSqm,
  formatRooms,
  formatDaysOnMarket,
} from '../../lib/formatters'
import { cn } from '../../lib/cn'

interface ListingCardProps {
  listing: Listing
  isNew: boolean
  isSelected: boolean
  onSelect: () => void
  onStatusChange: (status: string) => void
}

export function ListingCard({
  listing,
  isNew,
  isSelected,
  onSelect,
  onStatusChange,
}: ListingCardProps) {
  const imageUrl = listing.images?.[0] ?? null

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'group relative flex gap-0 rounded-xl overflow-hidden cursor-pointer',
        'border transition-all duration-150',
        isSelected
          ? 'border-[var(--accent)] shadow-md'
          : 'border-[var(--border)] hover:border-[oklch(78%_0.01_120)] hover:shadow-sm',
      )}
      style={{ background: 'white' }}
      onClick={onSelect}
    >
      {/* Image */}
      <div className="relative w-44 shrink-0 bg-[var(--accent-muted)]">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={listing.title}
            loading="lazy"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <span className="text-xs" style={{ color: 'var(--muted)' }}>kein Bild</span>
          </div>
        )}
        {isNew && (
          <span className="absolute top-2 left-2 w-2 h-2 rounded-full bg-[var(--status-new)]" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 p-4 flex flex-col gap-2">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-display font-semibold text-sm leading-snug line-clamp-2" style={{ color: 'var(--fg)' }}>
              {listing.title}
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>
              {listing.city ?? listing.address ?? '–'} · {listing.source}
            </p>
          </div>
          <ScoreBadge score={listing.lage_score} />
        </div>

        {/* Price row */}
        <div className="flex items-baseline gap-3">
          <span className="font-mono font-bold text-base" style={{ color: 'var(--accent)' }}>
            {formatPricePerSqm(listing.price_per_sqm)}
          </span>
          <span className="font-mono text-sm" style={{ color: 'var(--fg)' }}>
            {formatPrice(listing.price_eur)}
          </span>
        </div>

        {/* Specs row */}
        <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--muted)' }}>
          <span>{formatSqm(listing.qm)}</span>
          <span>·</span>
          <span>{formatRooms(listing.rooms)}</span>
          {listing.year_built && (
            <>
              <span>·</span>
              <span>Bj. {listing.year_built}</span>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 mt-auto">
          <StatusChip status={listing.status} />
          <span className="text-xs ml-auto" style={{ color: 'var(--muted)' }}>
            {formatDaysOnMarket(listing.first_seen_at)}
          </span>
        </div>
      </div>

      {/* Hover quick-actions */}
      <div
        className="absolute bottom-3 right-3 hidden group-hover:flex items-center gap-1"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={() => onStatusChange('interessant')}
          className="p-1.5 rounded-lg bg-white/90 border transition-colors hover:bg-[var(--accent-muted)]"
          style={{ borderColor: 'var(--border)' }}
          title="Interessant"
        >
          <Heart size={14} style={{ color: 'var(--accent)' }} />
        </button>
        <button
          onClick={() => onStatusChange('abgelehnt')}
          className="p-1.5 rounded-lg bg-white/90 border transition-colors hover:bg-[oklch(94%_0.04_25)]"
          style={{ borderColor: 'var(--border)' }}
          title="Ablehnen"
        >
          <X size={14} style={{ color: 'oklch(52% 0.180 25)' }} />
        </button>
        <a
          href={listing.url}
          target="_blank"
          rel="noopener noreferrer"
          className="p-1.5 rounded-lg bg-white/90 border transition-colors hover:bg-[var(--accent-muted)]"
          style={{ borderColor: 'var(--border)' }}
          title="Exposé öffnen"
        >
          <ArrowSquareOut size={14} style={{ color: 'var(--fg)' }} />
        </a>
      </div>
    </motion.article>
  )
}
