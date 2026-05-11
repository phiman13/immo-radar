import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cn } from '../../lib/cn'
import { fetchSettings, patchSetting } from '../../api/settings'
import { fetchCosts } from '../../api/system'
import type { ApiCosts } from '../../types'

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn('relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200')}
      style={{ background: checked ? 'var(--accent)' : 'var(--border)' }}
    >
      <span
        className="pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform duration-200"
        style={{ transform: checked ? 'translateX(16px)' : 'translateX(0)' }}
      />
    </button>
  )
}

export function MechanicsTab() {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const queryClient = useQueryClient()
  const s = data?.settings

  const { data: costs } = useQuery<ApiCosts>({
    queryKey: ['api-costs'],
    queryFn: fetchCosts,
    refetchInterval: 60_000,
  })

  const pollMut = useMutation({
    mutationFn: (v: number) => patchSetting('poll_interval_minutes', v),
    onSuccess: (d) => queryClient.setQueryData(['settings'], d),
  })

  const enrichMut = useMutation({
    mutationFn: (v: number) => patchSetting('detail_fetch_interval_minutes', v),
    onSuccess: (d) => queryClient.setQueryData(['settings'], d),
  })

  const pollEnabledMut = useMutation({
    mutationFn: (v: boolean) => patchSetting('poll_enabled', v),
    onSuccess: (d) => queryClient.setQueryData(['settings'], d),
  })

  const enrichEnabledMut = useMutation({
    mutationFn: (v: boolean) => patchSetting('enrich_enabled', v),
    onSuccess: (d) => queryClient.setQueryData(['settings'], d),
  })

  if (!s) return <div className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>Lade…</div>

  return (
    <div>
      <div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center justify-between mb-1">
          <p className="text-sm font-medium" style={{ color: 'var(--fg)' }}>Crawling (Poll)</p>
          <Toggle
            checked={s.poll_enabled ?? true}
            onChange={(v) => pollEnabledMut.mutate(v)}
          />
        </div>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Wie oft werden alle Quellen nach neuen Inseraten durchsucht?
        </p>
        <div className="flex items-center gap-3 flex-wrap" style={{ opacity: (s.poll_enabled ?? true) ? 1 : 0.4, pointerEvents: (s.poll_enabled ?? true) ? 'auto' : 'none' }}>
          {([
            [360, '6 Std.'], [720, '12 Std.'], [1440, '1 Tag'], [2880, '2 Tage'], [4320, '3 Tage'],
          ] as [number, string][]).map(([v, label]) => (
            <button
              key={v}
              onClick={() => pollMut.mutate(v)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium border transition-all"
              style={
                s.poll_interval_minutes === v
                  ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' }
                  : { color: 'var(--fg)', borderColor: 'var(--border)', background: 'white' }
              }
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="py-4">
        <div className="flex items-center justify-between mb-1">
          <p className="text-sm font-medium" style={{ color: 'var(--fg)' }}>Enrichment (KI-Scoring)</p>
          <Toggle
            checked={s.enrich_enabled ?? true}
            onChange={(v) => enrichEnabledMut.mutate(v)}
          />
        </div>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Wie oft werden Detaildaten (KI-Scoring, Lage) nachgeladen?
        </p>
        <div className="flex items-center gap-3 flex-wrap" style={{ opacity: (s.enrich_enabled ?? true) ? 1 : 0.4, pointerEvents: (s.enrich_enabled ?? true) ? 'auto' : 'none' }}>
          {([
            [720, '12 Std.'], [1440, '1 Tag'], [2880, '2 Tage'], [10080, '1 Woche'],
          ] as [number, string][]).map(([v, label]) => (
            <button
              key={v}
              onClick={() => enrichMut.mutate(v)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium border transition-all"
              style={
                s.detail_fetch_interval_minutes === v
                  ? { background: 'var(--accent)', color: 'white', borderColor: 'var(--accent)' }
                  : { color: 'var(--fg)', borderColor: 'var(--border)', background: 'white' }
              }
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="py-4 border-t mt-2" style={{ borderColor: 'var(--border)' }}>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>API-Kosten (Claude)</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Tatsächliche Anthropic-API-Kosten aus Token-Tracking
        </p>
        {costs ? (
          <div className="space-y-2">
            <div className="flex gap-6">
              <div>
                <p className="text-xs" style={{ color: 'var(--muted)' }}>Letzte 24h</p>
                <p className="font-mono text-sm font-semibold" style={{ color: 'var(--fg)' }}>
                  ${costs.last_24h.usd.toFixed(4)}
                </p>
                <p className="text-xs" style={{ color: 'var(--muted)' }}>{costs.last_24h.calls} Aufrufe</p>
              </div>
              <div>
                <p className="text-xs" style={{ color: 'var(--muted)' }}>Letzte 7 Tage</p>
                <p className="font-mono text-sm font-semibold" style={{ color: 'var(--fg)' }}>
                  ${costs.last_7d.usd.toFixed(4)}
                </p>
                <p className="text-xs" style={{ color: 'var(--muted)' }}>{costs.last_7d.calls} Aufrufe</p>
              </div>
            </div>
            <div className="flex gap-3 flex-wrap">
              {Object.entries(costs.breakdown_24h).map(([purpose, usd]) => (
                <span key={purpose} className="text-xs px-2 py-0.5 rounded" style={{ background: 'var(--border)', color: 'var(--muted)' }}>
                  {purpose === 'enrichment' ? 'Scoring' : purpose === 'analyze' ? 'Analyse' : 'Entdecken'}:&nbsp;
                  <span className="font-mono" style={{ color: 'var(--fg)' }}>${(usd as number).toFixed(4)}</span>
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-xs" style={{ color: 'var(--muted)' }}>Lade…</p>
        )}
      </div>
    </div>
  )
}
