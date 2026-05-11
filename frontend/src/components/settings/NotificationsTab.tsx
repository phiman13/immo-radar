import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle } from '@phosphor-icons/react'
import { fetchSettings, patchSetting } from '../../api/settings'
import { testTelegram } from '../../api/telegram'

export function NotificationsTab() {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const queryClient = useQueryClient()
  const s = data?.settings
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  const thresholdMut = useMutation({
    mutationFn: (v: number) => patchSetting('score_threshold', v),
    onSuccess: (d) => queryClient.setQueryData(['settings'], d),
  })

  const testMut = useMutation({
    mutationFn: testTelegram,
    onSuccess: (result) => setTestResult(result),
    onError: (e: Error) => setTestResult({ success: false, message: e.message }),
  })

  if (!s) return <div className="py-8 text-center text-sm" style={{ color: 'var(--muted)' }}>Lade…</div>

  return (
    <div>
      <div className="py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <p className="text-sm font-medium mb-1" style={{ color: 'var(--fg)' }}>Score-Schwelle für Alerts</p>
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          Nur Listings mit Lage-Score ≥ Schwelle lösen eine Telegram-Nachricht aus.
          0 = alle Listings benachrichtigen.
        </p>
        <div className="flex items-center gap-3">
          <input
            type="range" min={0} max={100} step={5}
            defaultValue={s.score_threshold}
            onMouseUp={(e) => thresholdMut.mutate(Number((e.target as HTMLInputElement).value))}
            className="w-48 accent-[var(--accent)]"
          />
          <span className="font-mono text-sm" style={{ color: 'var(--fg)' }}>
            {s.score_threshold === 0 ? 'Alle' : `≥ ${s.score_threshold}`}
          </span>
        </div>
      </div>

      <div className="py-4">
        <p className="text-sm font-medium mb-3" style={{ color: 'var(--fg)' }}>Telegram-Verbindung testen</p>
        <button
          onClick={() => testMut.mutate()}
          disabled={testMut.isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          style={{ background: 'var(--accent)' }}
        >
          {testMut.isPending ? 'Sende…' : 'Test-Nachricht senden'}
        </button>

        {testResult && (
          <div
            className="flex items-center gap-2 mt-3 p-3 rounded-lg text-sm"
            style={{
              background: testResult.success ? 'oklch(92% 0.04 145)' : 'oklch(94% 0.04 25)',
              color: testResult.success ? 'oklch(35% 0.13 145)' : 'oklch(38% 0.14 25)',
            }}
          >
            {testResult.success
              ? <CheckCircle size={16} />
              : <XCircle size={16} />}
            {testResult.message}
          </div>
        )}
      </div>
    </div>
  )
}
