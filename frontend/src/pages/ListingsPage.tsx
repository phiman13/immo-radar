import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence } from 'framer-motion'
import { SquaresFour, MapPin } from '@phosphor-icons/react'
import { fetchListings, patchListing } from '../api/listings'
import { fetchSources } from '../api/sources'
import { ListingCard } from '../components/listings/ListingCard'
import { FilterBar } from '../components/listings/FilterBar'
import { DetailPanel } from '../components/listings/DetailPanel'
import { ListingsMap } from '../components/map/ListingsMap'
import { useUIStore } from '../store/ui'
import { useLastVisit, isNewSinceLastVisit } from '../hooks/useLastVisit'
import { cn } from '../lib/cn'
import type { Listing } from '../types'

export function ListingsPage() {
  const { filter, selectedListingId, setSelectedListingId, viewMode, setViewMode } = useUIStore()
  const lastVisit = useLastVisit()
  const queryClient = useQueryClient()

  const { data: listings = [], isLoading } = useQuery({
    queryKey: ['listings', filter],
    queryFn: () =>
      fetchListings({
        status: filter.status || undefined,
        portal: filter.portal || undefined,
        min_score: filter.minScore || undefined,
        price_min: filter.priceMin,
        price_max: filter.priceMax,
        qm_min: filter.qmMin,
        qm_max: filter.qmMax,
        rooms_min: filter.roomsMin,
        sort: filter.sort,
      }),
  })

  const { data: sources = [] } = useQuery({
    queryKey: ['sources'],
    queryFn: fetchSources,
  })

  const patchMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      patchListing(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['listings'] })
    },
  })

  const selectedListing: Listing | null =
    listings.find((l) => l.id === selectedListingId) ?? null


  function handleStatusChange(id: number, status: string) {
    patchMutation.mutate({ id, status })
    queryClient.setQueryData<Listing[]>(['listings', filter], (prev) =>
      prev?.map((l) => (l.id === id ? { ...l, status } : l)),
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 rounded-full border-2 animate-spin"
          style={{ borderColor: 'var(--border)', borderTopColor: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="flex flex-col min-h-[100dvh]">
      <FilterBar sources={sources} />

      <div className="flex-1 px-6 py-4">
        {/* Header row: count + view toggle */}
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm" style={{ color: 'var(--muted)' }}>
            {listings.length} {listings.length === 1 ? 'Objekt' : 'Objekte'}
          </p>
          <div className="flex items-center gap-1 rounded-lg border p-0.5" style={{ borderColor: 'var(--border)' }}>
            <button
              onClick={() => setViewMode('grid')}
              className={cn(
                'p-1.5 rounded transition-colors',
                viewMode === 'grid'
                  ? 'bg-[--accent] text-white'
                  : 'hover:text-[--fg]',
              )}
              style={viewMode !== 'grid' ? { color: 'var(--muted)' } : undefined}
              title="Listenansicht"
            >
              <SquaresFour size={16} weight="fill" />
            </button>
            <button
              onClick={() => setViewMode('map')}
              className={cn(
                'p-1.5 rounded transition-colors',
                viewMode === 'map'
                  ? 'bg-[--accent] text-white'
                  : 'hover:text-[--fg]',
              )}
              style={viewMode !== 'map' ? { color: 'var(--muted)' } : undefined}
              title="Kartenansicht"
            >
              <MapPin size={16} weight="fill" />
            </button>
          </div>
        </div>

        {listings.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="font-display text-xl font-semibold mb-2" style={{ color: 'var(--fg)' }}>
              Keine Objekte gefunden
            </p>
            <p className="text-sm" style={{ color: 'var(--muted)' }}>
              Filter anpassen oder warten bis der nächste Crawl läuft.
            </p>
          </div>
        ) : viewMode === 'map' ? (
          <>
            <div className="relative rounded-lg overflow-hidden border" style={{ height: 'calc(100vh - 200px)', borderColor: 'var(--border)' }}>
              <ListingsMap
                listings={listings}
                selectedId={selectedListingId}
                onListingClick={setSelectedListingId}
              />
            </div>
            {listings.filter((l) => !l.lat || !l.lon).length > 0 && (
              <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>
                {listings.filter((l) => !l.lat || !l.lon).length} Objekte ohne Koordinaten werden nicht auf der Karte angezeigt.
              </p>
            )}
          </>
        ) : (
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {listings.map((listing) => (
                <ListingCard
                  key={listing.id}
                  listing={listing}
                  isNew={isNewSinceLastVisit(listing.first_seen_at, lastVisit)}
                  isSelected={listing.id === selectedListingId}
                  onSelect={() =>
                    setSelectedListingId(
                      listing.id === selectedListingId ? null : listing.id,
                    )
                  }
                  onStatusChange={(status) => handleStatusChange(listing.id, status)}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      <DetailPanel
        listing={selectedListing}
        onClose={() => setSelectedListingId(null)}
        onStatusChange={handleStatusChange}
      />
    </div>
  )
}
