import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSources, patchSource } from '../../api/sources'
import { formatTimeAgo } from '../../lib/formatters'

export function SourcesTab() {
  const queryClient = useQueryClient()
  const { data: sources = [] } = useQuery({ queryKey: ['sources'], queryFn: fetchSources })

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      patchSource(id, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sources'] }),
  })

  return (
    <div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left" style={{ color: 'var(--muted)' }}>
            <th className="py-3 font-medium text-xs">Quelle</th>
            <th className="py-3 font-medium text-xs">Letzter Crawl</th>
            <th className="py-3 font-medium text-xs text-right">Inserate</th>
            <th className="py-3 font-medium text-xs text-right">Aktiv</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id} className="border-t" style={{ borderColor: 'var(--border)' }}>
              <td className="py-3 font-medium" style={{ color: 'var(--fg)' }}>
                {source.display_name}
              </td>
              <td className="py-3" style={{ color: 'var(--muted)' }}>
                {source.last_run ? formatTimeAgo(source.last_run) : '–'}
              </td>
              <td className="py-3 text-right font-mono text-xs" style={{ color: 'var(--fg)' }}>
                {source.listing_count}
              </td>
              <td className="py-3 text-right">
                <button
                  onClick={() => toggleMut.mutate({ id: source.id, enabled: !source.enabled })}
                  className="relative inline-flex h-5 w-9 rounded-full transition-colors"
                  style={{
                    background: source.enabled ? 'var(--accent)' : 'var(--border)',
                  }}
                  aria-label={source.enabled ? 'Deaktivieren' : 'Aktivieren'}
                >
                  <span
                    className="inline-block h-4 w-4 rounded-full bg-white shadow transition-transform my-0.5"
                    style={{ transform: source.enabled ? 'translateX(20px)' : 'translateX(2px)' }}
                  />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
