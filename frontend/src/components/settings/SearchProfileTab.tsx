import { type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, patchSetting } from '../../api/settings'
import type { AppSettings } from '../../types'
import { cn } from '../../lib/cn'
import { LocationPicker } from '../map/LocationPicker'

const PROPERTY_TYPES = ['Wohnung', 'Haus', 'Doppelhaushälfte', 'Reihenhaus', 'Grundstück']

function useSetting<K extends keyof AppSettings>(key: K) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (value: AppSettings[K]) => patchSetting(key, value),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
    },
  })
  return mutation
}

interface RowProps {
  label: string
  hint?: string
  children: ReactNode
}

function Row({ label, hint, children }: RowProps) {
  return (
    <div className="flex items-center justify-between py-4 border-b" style={{ borderColor: 'var(--border)' }}>
      <div>
        <p className="text-sm font-medium" style={{ color: 'var(--fg)' }}>{label}</p>
        {hint && <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>{hint}</p>}
      </div>
      <div className="ml-6 shrink-0">{children}</div>
    </div>
  )
}

export function SearchProfileTab() {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const s = data?.settings

  const centerLatMut = useSetting('search_center_lat')
  const centerLonMut = useSetting('search_center_lon')
  const radiusMut = useSetting('search_radius_km')
  const priceMinMut = useSetting('price_min')
  const priceMaxMut = useSetting('price_max')
  const roomsMut = useSetting('rooms_min')
  const yearBuiltMut = useSetting('year_built_min')
  const queryClient = useQueryClient()
  const propertyTypesMut = useMutation({
    mutationFn: (types: string[]) => patchSetting('property_types', types.join(',')),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
    },
  })

  if (!s) return <div className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>Lade…</div>

  return (
    <div>
      <div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Suchgebiet</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Mittelpunkt verschieben oder Ort suchen · Radius per Slider anpassen
        </p>
        <LocationPicker
          lat={s.search_center_lat ?? 47.9095}
          lon={s.search_center_lon ?? 11.2783}
          radiusKm={s.search_radius_km ?? 5}
          onChangeCenter={(lat, lon) => {
            centerLatMut.mutate(lat)
            centerLonMut.mutate(lon)
          }}
          onChangeRadius={(km) => radiusMut.mutate(km)}
        />
      </div>

      <Row label="Preisuntergrenze" hint="Minimum-Kaufpreis">
        <div className="flex items-center gap-2">
          <input
            type="number" step={10000} min={0} max={s.price_max}
            defaultValue={s.price_min}
            onBlur={(e) => priceMinMut.mutate(Number(e.target.value))}
            className="w-32 text-sm font-mono px-2 py-1 rounded-lg border text-right"
            style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
          />
          <span className="text-xs" style={{ color: 'var(--muted)' }}>€</span>
        </div>
      </Row>

      <Row label="Preisobergrenze" hint="Maximum-Kaufpreis">
        <div className="flex items-center gap-2">
          <input
            type="number" step={10000} min={s.price_min} max={5000000}
            defaultValue={s.price_max}
            onBlur={(e) => priceMaxMut.mutate(Number(e.target.value))}
            className="w-32 text-sm font-mono px-2 py-1 rounded-lg border text-right"
            style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
          />
          <span className="text-xs" style={{ color: 'var(--muted)' }}>€</span>
        </div>
      </Row>

      <Row label="Mindest-Zimmer" hint="Minimum Zimmeranzahl">
        <select
          defaultValue={s.rooms_min}
          onChange={(e) => roomsMut.mutate(Number(e.target.value))}
          className="text-sm px-2 py-1 rounded-lg border"
          style={{ borderColor: 'var(--border)', color: 'var(--fg)' }}
        >
          {[0, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5].map((r) => (
            <option key={r} value={r}>{r === 0 ? 'Egal' : `≥ ${r} Zi.`}</option>
          ))}
        </select>
      </Row>

      <Row label="Baujahr ab" hint="Mindest-Baujahr des Objekts">
        <div className="flex items-center gap-3">
          <input
            type="range" min={1850} max={2030} step={5}
            defaultValue={s.year_built_min ?? 1980}
            onMouseUp={(e) => yearBuiltMut.mutate(Number((e.target as HTMLInputElement).value))}
            className="w-32 accent-[var(--accent)]"
          />
          <span className="font-mono text-sm w-12 text-right" style={{ color: 'var(--fg)' }}>
            {s.year_built_min ?? 1980}
          </span>
        </div>
      </Row>

      <Row label="Objekttypen" hint="Nur diese Typen berücksichtigen">
        <div className="flex flex-wrap gap-2 max-w-xs justify-end">
          {PROPERTY_TYPES.map((pt) => {
            const active = (s.property_types ?? []).includes(pt)
            return (
              <button
                key={pt}
                type="button"
                onClick={() => {
                  const current = s.property_types ?? []
                  const next = active
                    ? current.filter((t) => t !== pt)
                    : [...current, pt]
                  propertyTypesMut.mutate(next)
                }}
                className={cn(
                  'px-3 py-1 rounded-full text-xs border transition-colors',
                  active
                    ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                    : 'border-[var(--border)] hover:border-[var(--accent)]'
                )}
                style={active ? {} : { color: 'var(--muted)' }}
              >
                {pt}
              </button>
            )
          })}
        </div>
      </Row>
    </div>
  )
}
