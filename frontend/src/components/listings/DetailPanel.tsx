import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, ArrowSquareOut, Warning } from '@phosphor-icons/react'
import type { Listing } from '../../types'
import { ScoreBadge } from './ScoreBadge'
import {
  formatPrice,
  formatPricePerSqm,
  formatSqm,
  formatRooms,
  formatDaysOnMarket,
} from '../../lib/formatters'
import { patchListing } from '../../api/listings'
import { STATUS_LABELS } from '../../types'
import { ListingMiniMap } from '../map/ListingMiniMap'

interface DetailPanelProps {
  listing: Listing | null
  onClose: () => void
  onStatusChange: (id: number, status: string) => void
}

export function DetailPanel({ listing, onClose, onStatusChange }: DetailPanelProps) {
  const [notes, setNotes] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    if (listing) setNotes(listing.notes ?? '')
  }, [listing?.id])

  function handleNotesChange(value: string) {
    setNotes(value)
    clearTimeout(debounceRef.current)
    if (listing) {
      debounceRef.current = setTimeout(() => {
        patchListing(listing.id, { notes: value })
      }, 1_000)
    }
  }

  function handleStatusChange(status: string) {
    if (!listing) return
    patchListing(listing.id, { status })
    onStatusChange(listing.id, status)
  }

  return (
    <AnimatePresence>
      {listing && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-30"
            style={{ background: 'oklch(18% 0.010 240 / 0.15)' }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 300 }}
            className="fixed right-0 top-0 h-full w-[420px] z-40 overflow-y-auto flex flex-col"
            style={{ background: 'white', borderLeft: '1px solid var(--border)' }}
          >
            {/* Header */}
            <div className="sticky top-0 z-10 flex items-start gap-3 p-5 border-b" style={{ background: 'white', borderColor: 'var(--border)' }}>
              <div className="flex-1 min-w-0">
                <p className="font-display font-bold text-lg leading-tight line-clamp-2" style={{ color: 'var(--fg)' }}>
                  {listing.title}
                </p>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="font-mono font-bold text-xl" style={{ color: 'var(--accent)' }}>
                    {formatPricePerSqm(listing.price_per_sqm)}
                  </span>
                  <span className="font-mono text-sm" style={{ color: 'var(--fg)' }}>
                    {formatPrice(listing.price_eur)}
                  </span>
                </div>
                <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>
                  {formatDaysOnMarket(listing.first_seen_at)} online · {listing.source}
                </p>
              </div>
              <button
                onClick={onClose}
                className="shrink-0 p-1.5 rounded-lg transition-colors hover:bg-[var(--accent-muted)]"
                style={{ color: 'var(--muted)' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 p-5 flex flex-col gap-6">
              {/* Image gallery */}
              {listing.images.length > 0 && (
                <div className="flex gap-2 overflow-x-auto pb-1 -mx-5 px-5">
                  {listing.images.slice(0, 6).map((src, i) => (
                    <img
                      key={i}
                      src={src}
                      alt=""
                      className="h-40 w-auto rounded-lg shrink-0 object-cover"
                    />
                  ))}
                </div>
              )}

              {/* Key data */}
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Fläche', value: formatSqm(listing.qm) },
                  { label: 'Zimmer', value: formatRooms(listing.rooms) },
                  { label: 'Baujahr', value: listing.year_built ? String(listing.year_built) : '–' },
                  { label: 'Typ', value: listing.property_type ?? '–' },
                  { label: 'Hausgeld', value: listing.hausgeld_eur ? formatPrice(listing.hausgeld_eur) + '/Mo.' : '–' },
                  { label: 'Energie', value: listing.energie_class ? `${listing.energie_class}${listing.energie_kwh ? ` · ${Math.round(listing.energie_kwh)} kWh` : ''}` : '–' },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <p className="text-xs" style={{ color: 'var(--muted)' }}>{label}</p>
                    <p className="font-mono text-sm font-medium" style={{ color: 'var(--fg)' }}>{value}</p>
                  </div>
                ))}
              </div>

              {/* Address */}
              {listing.address && (
                <div>
                  <p className="text-xs mb-1" style={{ color: 'var(--muted)' }}>Adresse</p>
                  <p className="text-sm" style={{ color: 'var(--fg)' }}>{listing.address}</p>
                </div>
              )}

              {/* Minimap */}
              {listing.lat && listing.lon && (
                <ListingMiniMap lat={listing.lat} lon={listing.lon} />
              )}

              {/* AI Score + Reasoning */}
              <div className="flex items-start gap-3 p-4 rounded-xl" style={{ background: 'var(--bg)' }}>
                <ScoreBadge score={listing.lage_score} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium mb-1" style={{ color: 'var(--fg)' }}>KI-Bewertung</p>
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--muted)' }}>
                    {listing.ai_reasoning ?? 'Noch keine KI-Bewertung.'}
                  </p>
                </div>
              </div>

              {/* Risk flags */}
              {listing.risk_flags.length > 0 && (
                <div>
                  <p className="text-xs mb-2" style={{ color: 'var(--muted)' }}>Risiken</p>
                  <div className="flex flex-wrap gap-1.5">
                    {listing.risk_flags.map((flag) => (
                      <span
                        key={flag}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs"
                        style={{ background: 'oklch(94% 0.04 25)', color: 'oklch(38% 0.14 25)' }}
                      >
                        <Warning size={11} />
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Status selector */}
              <div>
                <p className="text-xs mb-2" style={{ color: 'var(--muted)' }}>Status</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(STATUS_LABELS).map(([value, label]) => (
                    <button
                      key={value}
                      onClick={() => handleStatusChange(value)}
                      className="px-3 py-1 rounded-full text-xs font-medium border transition-all"
                      style={
                        listing.status === value
                          ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' }
                          : { background: 'white', color: 'var(--fg)', borderColor: 'var(--border)' }
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Notes */}
              <div>
                <p className="text-xs mb-2" style={{ color: 'var(--muted)' }}>Notizen</p>
                <textarea
                  value={notes}
                  onChange={(e) => handleNotesChange(e.target.value)}
                  placeholder="Persönliche Notizen…"
                  rows={4}
                  className="w-full text-sm p-3 rounded-xl border resize-none focus:outline-none focus:ring-1"
                  style={{
                    borderColor: 'var(--border)',
                    color: 'var(--fg)',
                    background: 'var(--bg)',
                    fontFamily: 'inherit',
                  }}
                />
              </div>
            </div>

            {/* Footer CTA */}
            <div className="sticky bottom-0 p-4 border-t" style={{ background: 'white', borderColor: 'var(--border)' }}>
              <a
                href={listing.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium text-white transition-opacity hover:opacity-90"
                style={{ background: 'var(--accent)' }}
              >
                Exposé öffnen
                <ArrowSquareOut size={16} />
              </a>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
