import { type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, patchSetting } from '../../api/settings'
import type { AppSettings } from '../../types'
import { cn } from '../../lib/cn'
import { MultiLocationPicker, type SearchLocation } from '../map/MultiLocationPicker'

// Anzeige-Label -> Backend-Enum-Wert (app.models.PropertyType, lowercase/
// ASCII). HER-808: die Chips glichen bisher die deutschen UI-Labels direkt
// (mit Umlauten/Großschreibung) gegen s.property_types ab -- das matcht die
// tatsächlichen Backend-Werte nie, kein Chip zeigte je "aktiv", ein Klick
// hängte das falsch geschriebene Label als zusätzlichen, nie wieder
// entfernbaren Eintrag an.
const PROPERTY_TYPES: { label: string; value: string }[] = [
  { label: 'Wohnung', value: 'wohnung' },
  { label: 'Haus', value: 'haus' },
  { label: 'Doppelhaushälfte', value: 'doppelhaushaelfte' },
  { label: 'Reihenhaus', value: 'reihenhaus' },
  { label: 'Grundstück', value: 'grundstueck' },
]
const PREFERENCE_CHIPS = ['Balkon', 'Terrasse', 'Garten', 'Garage/Stellplatz', 'Keller', 'Aufzug', 'Einbauküche', 'Barrierefrei']

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

  const locationsMut = useMutation({
    mutationFn: (locations: SearchLocation[]) =>
      patchSetting('search_locations', locations),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
    },
  })
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
  const preferencesMut = useMutation({
    mutationFn: (prefs: string[]) => patchSetting('preferences', prefs),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
    },
  })

  if (!s) return <div className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>Lade…</div>

  return (
    <div>
      <div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Suchgebiete</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Mehrere Standorte möglich · Marker verschieben oder Ort suchen · Radius per Slider
        </p>
        <MultiLocationPicker
          locations={
            s.search_locations?.length
              ? s.search_locations
              : [{ lat: s.search_center_lat ?? 47.9095, lon: s.search_center_lon ?? 11.2783, radius_km: s.search_radius_km ?? 5, label: 'Hauptstandort' }]
          }
          onChange={(locs) => locationsMut.mutate(locs)}
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
          {PROPERTY_TYPES.map(({ label, value }) => {
            const current = s.property_types ?? []
            const active = current.includes(value)
            return (
              <button
                key={value}
                type="button"
                onClick={() => {
                  const next = active
                    ? current.filter((t) => t !== value)
                    : [...current, value]
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
                {label}
              </button>
            )
          })}
        </div>
      </Row>

      <Row label="KI-Ausstattungs-Präferenzen" hint="Fließt in KI-Score ein — kein harter Filter">
        <div className="flex flex-wrap gap-2 max-w-xs justify-end">
          {PREFERENCE_CHIPS.map((pref) => {
            const active = (s.preferences ?? []).includes(pref)
            return (
              <button
                key={pref}
                type="button"
                onClick={() => {
                  const current = s.preferences ?? []
                  const next = active
                    ? current.filter((p) => p !== pref)
                    : [...current, pref]
                  preferencesMut.mutate(next)
                }}
                className={cn(
                  'px-3 py-1 rounded-full text-xs border transition-colors',
                  active
                    ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                    : 'border-[var(--border)] hover:border-[var(--accent)]'
                )}
                style={active ? {} : { color: 'var(--muted)' }}
              >
                {pref}
              </button>
            )
          })}
        </div>
      </Row>
    </div>
  )
}
