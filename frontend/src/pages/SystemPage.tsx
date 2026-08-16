import { useQuery, useMutation } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import { Play } from '@phosphor-icons/react'
import { fetchSystemStatus, fetchFetchRuns, triggerCrawl } from '../api/system'
import { formatTimeAgo } from '../lib/formatters'

export function SystemPage() {
  const [isCrawling, setIsCrawling] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['system-status'],
    queryFn: fetchSystemStatus,
    refetchInterval: 30_000,
  })

  const { data: runs = [], refetch: refetchRuns } = useQuery({
    queryKey: ['fetch-runs'],
    queryFn: fetchFetchRuns,
    refetchInterval: 30_000,
  })

  const triggerMut = useMutation({
    mutationFn: triggerCrawl,
    onSuccess: () => {
      setIsCrawling(true)
      if (pollRef.current) clearInterval(pollRef.current)
      let count = 0
      pollRef.current = setInterval(() => {
        refetchRuns()
        refetchStatus()
        if (++count >= 12) {
          clearInterval(pollRef.current!)
          setIsCrawling(false)
        }
      }, 2_500)
    },
  })

  const totalListings = status?.listing_counts.total ?? 0

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--fg)' }}>
          System
        </h1>
        <button
          onClick={() => triggerMut.mutate()}
          disabled={triggerMut.isPending || isCrawling}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white disabled:opacity-50 transition-opacity hover:opacity-90"
          style={{ background: 'var(--accent)' }}
        >
          <Play size={14} />
          {isCrawling ? 'Läuft…' : 'Jetzt crawlen'}
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: 'Gesamt', value: totalListings },
          { label: 'Interessant', value: status?.listing_counts.interessant ?? 0 },
          { label: 'Neu (heute)', value: status?.listing_counts.new ?? 0 },
        ].map(({ label, value }) => (
          <div key={label} className="p-4 rounded-xl border" style={{ borderColor: 'var(--border)', background: 'white' }}>
            <p className="text-xs" style={{ color: 'var(--muted)' }}>{label}</p>
            <p className="font-mono text-2xl font-bold mt-1" style={{ color: 'var(--fg)' }}>{value}</p>
          </div>
        ))}
      </div>

      {/* Scheduler */}
      <div className="p-4 rounded-xl border mb-8" style={{ borderColor: 'var(--border)', background: 'white' }}>
        <div className="flex items-center gap-2 mb-3">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: status?.scheduler_running ? 'var(--status-new)' : 'var(--status-rejected)' }}
          />
          <p className="text-sm font-medium" style={{ color: 'var(--fg)' }}>
            Scheduler {status?.scheduler_running ? 'aktiv' : 'inaktiv'}
          </p>
        </div>
        {status && !status.jobs_available && (
          <p className="text-xs" style={{ color: 'var(--muted)' }}>
            Job-Zeitpläne sind nur im Worker-Prozess einsehbar, nicht über dieses Dashboard.
          </p>
        )}
        {status?.jobs.map((job) => (
          <div key={job.id} className="flex justify-between text-xs" style={{ color: 'var(--muted)' }}>
            <span>{job.id}</span>
            <span>{job.next_run ? `nächster Run: ${formatTimeAgo(job.next_run)}` : '–'}</span>
          </div>
        ))}
      </div>

      {/* FetchRuns table */}
      <h2 className="font-display text-lg font-semibold mb-3" style={{ color: 'var(--fg)' }}>
        Letzte Crawls
      </h2>
      <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
        <table className="w-full text-sm">
          <thead style={{ background: 'var(--bg)' }}>
            <tr style={{ color: 'var(--muted)' }}>
              <th className="text-left px-4 py-2.5 text-xs font-medium">Quelle</th>
              <th className="text-left px-4 py-2.5 text-xs font-medium">Start</th>
              <th className="text-right px-4 py-2.5 text-xs font-medium" title="Alle gescrapten Inserate vor Profil-Filter">Gescrapt</th>
              <th className="text-right px-4 py-2.5 text-xs font-medium" title="Neu in DB (nach Filter)">Neu</th>
              <th className="text-right px-4 py-2.5 text-xs font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {runs.slice(0, 20).map((run) => (
              <tr key={run.id} className="border-t" style={{ borderColor: 'var(--border)', background: 'white' }}>
                <td className="px-4 py-2.5 font-medium" style={{ color: 'var(--fg)' }}>{run.source}</td>
                <td className="px-4 py-2.5" style={{ color: 'var(--muted)' }}>
                  {formatTimeAgo(run.started_at)}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs" style={{ color: 'var(--fg)' }}>
                  {run.listings_found}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs" style={{ color: run.listings_new > 0 ? 'var(--status-new)' : 'var(--muted)' }}>
                  {run.listings_new > 0 ? `+${run.listings_new}` : '0'}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {run.error ? (
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'oklch(94% 0.04 25)', color: 'oklch(38% 0.14 25)' }}>
                      Fehler
                    </span>
                  ) : (
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'oklch(92% 0.04 145)', color: 'oklch(35% 0.13 145)' }}>
                      OK
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {runs.length === 0 && (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--muted)' }}>
            Noch keine Crawls gelaufen.
          </div>
        )}
      </div>
    </div>
  )
}
