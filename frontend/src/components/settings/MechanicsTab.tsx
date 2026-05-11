import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, patchSetting } from '../../api/settings'

export function MechanicsTab() {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const queryClient = useQueryClient()
  const s = data?.settings

  const pollMut = useMutation({
    mutationFn: (v: number) => patchSetting('poll_interval_minutes', v),
    onSuccess: (d) => queryClient.setQueryData(['settings'], d),
  })

  const enrichMut = useMutation({
    mutationFn: (v: number) => patchSetting('detail_fetch_interval_minutes', v),
    onSuccess: (d) => queryClient.setQueryData(['settings'], d),
  })

  if (!s) return <div className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>Lade…</div>

  return (
    <div>
      <div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Poll-Intervall</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Wie oft werden alle Quellen nach neuen Inseraten durchsucht?
        </p>
        <div className="flex items-center gap-3">
          {[5, 10, 15, 30, 60].map((v) => (
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
              {v} Min
            </button>
          ))}
        </div>
      </div>

      <div className="py-4">
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Enrichment-Intervall</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Wie oft werden Detaildaten (KI-Scoring, Lage) nachgeladen?
        </p>
        <div className="flex items-center gap-3">
          {[30, 60, 120].map((v) => (
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
              {v} Min
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
