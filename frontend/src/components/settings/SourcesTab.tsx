import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, MagnifyingGlass, CircleNotch, Lock } from '@phosphor-icons/react'
import {
  fetchSources,
  patchSource,
  analyzeSource,
  discoverSources,
  createSource,
} from '../../api/sources'
import type { AnalyzeResult, DiscoverSuggestion } from '../../api/sources'
import { formatTimeAgo } from '../../lib/formatters'
import { cn } from '../../lib/cn'

function AnalyzeFlow({ onAdded }: { onAdded: () => void }) {
  const [url, setUrl] = useState('')
  const [state, setState] = useState<'idle' | 'loading' | 'result' | 'saved'>('idle')
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleAnalyze() {
    if (!url.trim()) return
    setState('loading')
    setError(null)
    try {
      const r = await analyzeSource(url)
      setResult(r)
      if (r.error) {
        setError(r.error)
        setState('idle')
      } else {
        setState('result')
        try {
          setName(new URL(r.url).hostname.replace('www.', ''))
        } catch {
          setName('')
        }
      }
    } catch (e) {
      setError(String(e))
      setState('idle')
    }
  }

  async function handleSave() {
    if (!result || !name.trim()) return
    setSaving(true)
    try {
      await createSource({
        name: name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
        display_name: name,
        url: result.url,
        source_type: 'suggested',
      })
      setState('saved')
      onAdded()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  if (state === 'saved') return (
    <div className="text-sm text-[--accent] flex items-center gap-2">
      <CheckCircle size={16} weight="fill" /> Quelle gespeichert als Vorschlag.
      <button
        onClick={() => { setState('idle'); setUrl(''); setResult(null); setName('') }}
        className="ml-2 text-[--muted] underline text-xs"
      >
        Weitere hinzufügen
      </button>
    </div>
  )

  return (
    <div className="space-y-3">
      <label className="block text-xs text-[--muted]">URL der Immobilien-Seite</label>
      <div className="flex gap-2">
        <input
          type="url"
          placeholder="https://makler-xyz.de/immobilien"
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
          disabled={state === 'loading'}
          className="flex-1 px-3 py-2 rounded-lg border border-[--border] text-sm focus:outline-none focus:border-[--accent] bg-white"
        />
        <button
          onClick={handleAnalyze}
          disabled={state === 'loading' || !url.trim()}
          className="px-4 py-2 rounded-lg bg-[--accent] text-white text-sm font-medium disabled:opacity-50 flex items-center gap-2"
        >
          {state === 'loading'
            ? <><CircleNotch size={14} className="animate-spin" /> Analysiere…</>
            : 'Analysieren'
          }
        </button>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {state === 'result' && result && (
        <div className="rounded-lg border border-[--border] p-4 space-y-3 bg-white">
          {result.listing_count > 0 ? (
            <>
              <p className="text-sm font-medium text-[--fg]">
                ~{result.listing_count} Inserate gefunden
                {result.example_title && (
                  <span className="font-normal text-[--muted]">
                    {' · Beispiel: "'}
                    {result.example_title}
                    {result.example_price ? `, ${result.example_price}` : ''}
                    {'"'}
                  </span>
                )}
              </p>
              <div className="flex gap-2 flex-wrap">
                {(['price', 'qm', 'rooms', 'address', 'images'] as const).map(field => (
                  <span key={field} className={cn(
                    'px-2 py-0.5 rounded text-xs',
                    result.fields[field]
                      ? 'bg-[--accent-muted] text-[--accent]'
                      : 'bg-[--border] text-[--muted] line-through'
                  )}>
                    {field === 'price' ? 'Preis' : field === 'qm' ? 'm²' : field === 'rooms' ? 'Zimmer' : field === 'address' ? 'Adresse' : 'Bilder'}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-[--muted]">Keine Inserate erkannt — möglicherweise kein Immobilien-Portal oder Seite erfordert JavaScript.</p>
          )}

          {result.listing_count > 0 && (
            <div className="flex gap-2 items-center pt-1">
              <input
                type="text"
                placeholder="Name der Quelle"
                value={name}
                onChange={e => setName(e.target.value)}
                className="flex-1 px-3 py-1.5 rounded border border-[--border] text-sm focus:outline-none focus:border-[--accent] bg-white"
              />
              <button
                onClick={handleSave}
                disabled={!name.trim() || saving}
                className="px-4 py-1.5 rounded bg-[--accent] text-white text-sm font-medium disabled:opacity-50"
              >
                {saving ? 'Speichern…' : 'Aufnehmen'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DiscoverFlow({ onAdded }: { onAdded: () => void }) {
  const [state, setState] = useState<'idle' | 'loading' | 'result'>('idle')
  const [suggestions, setSuggestions] = useState<DiscoverSuggestion[]>([])
  const [saved, setSaved] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  async function handleDiscover() {
    setState('loading')
    setError(null)
    try {
      const results = await discoverSources()
      setSuggestions(results)
      setState('result')
    } catch (e) {
      setError(String(e))
      setState('idle')
    }
  }

  async function handleAdd(s: DiscoverSuggestion) {
    try {
      await createSource({
        name: s.name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
        display_name: s.name,
        url: s.url,
        source_type: 'suggested',
      })
      setSaved(prev => new Set(prev).add(s.name))
      onAdded()
    } catch {
      // 409 = already exists — mark as saved anyway
      setSaved(prev => new Set(prev).add(s.name))
    }
  }

  return (
    <div className="space-y-3">
      <button
        onClick={handleDiscover}
        disabled={state === 'loading'}
        className="w-full px-4 py-2.5 rounded-lg border border-[--border] text-sm text-[--fg] hover:border-[--accent] hover:text-[--accent] transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
      >
        {state === 'loading'
          ? <><CircleNotch size={14} className="animate-spin" /> Claude sucht nach Quellen…</>
          : <><MagnifyingGlass size={16} /> Neue Quellen für meine Region entdecken</>
        }
      </button>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {state === 'result' && suggestions.length > 0 && (
        <div className="rounded-lg border border-[--border] divide-y divide-[--border] bg-white">
          {suggestions.map(s => (
            <div key={s.name} className="flex items-center gap-3 px-4 py-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[--fg]">{s.name}</p>
                <p className="text-xs text-[--muted] truncate">{s.description}</p>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-[--accent] hover:underline truncate block mt-0.5"
                  onClick={e => e.stopPropagation()}
                >
                  {s.url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}
                </a>
              </div>
              {saved.has(s.name) ? (
                <span className="text-xs text-[--accent] flex items-center gap-1">
                  <CheckCircle size={14} weight="fill" /> Gespeichert
                </span>
              ) : (
                <button
                  onClick={() => handleAdd(s)}
                  className="text-xs px-3 py-1 rounded border border-[--accent] text-[--accent] hover:bg-[--accent-muted] transition-colors whitespace-nowrap"
                >
                  Aufnehmen
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

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
            <tr
              key={source.id}
              className="border-t"
              style={{
                borderColor: 'var(--border)',
                opacity: source.source_type === 'blocked' ? 0.55 : 1,
              }}
            >
              <td className="py-3 font-medium" style={{ color: 'var(--fg)' }}>
                {source.display_name}
                {source.source_type === 'blocked' && (
                  <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                    Gesperrt
                  </span>
                )}
                {source.source_type === 'suggested' && (
                  <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-[--border] text-[--muted]">Vorschlag</span>
                )}
              </td>
              <td className="py-3" style={{ color: 'var(--muted)' }}>
                {source.source_type === 'blocked'
                  ? <span className="text-xs" title="Bot-Schutz — scraping nicht möglich">–</span>
                  : source.last_run ? formatTimeAgo(source.last_run) : '–'
                }
              </td>
              <td className="py-3 text-right font-mono text-xs" style={{ color: 'var(--fg)' }}>
                {source.source_type === 'blocked' ? '–' : source.listing_count}
              </td>
              <td className="py-3 text-right">
                {source.source_type === 'blocked' ? (
                  <Lock size={16} style={{ color: 'var(--muted)' }} className="ml-auto" />
                ) : (
                  <button
                    onClick={() => toggleMut.mutate({ id: source.id, enabled: !source.enabled })}
                    className="relative inline-flex h-5 w-9 rounded-full transition-colors"
                    style={{ background: source.enabled ? 'var(--accent)' : 'var(--border)' }}
                    aria-label={source.enabled ? 'Deaktivieren' : 'Aktivieren'}
                  >
                    <span
                      className="inline-block h-4 w-4 rounded-full bg-white shadow transition-transform my-0.5"
                      style={{ transform: source.enabled ? 'translateX(20px)' : 'translateX(2px)' }}
                    />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* --- Neue Quelle hinzufügen --- */}
      <div className="mt-8 border-t border-[--border] pt-6">
        <h3 className="text-sm font-semibold text-[--fg] mb-4">Neue Quelle hinzufügen</h3>
        <AnalyzeFlow onAdded={() => queryClient.invalidateQueries({ queryKey: ['sources'] })} />
        <div className="flex items-center gap-3 my-5">
          <div className="flex-1 h-px bg-[--border]" />
          <span className="text-xs text-[--muted]">oder</span>
          <div className="flex-1 h-px bg-[--border]" />
        </div>
        <DiscoverFlow onAdded={() => queryClient.invalidateQueries({ queryKey: ['sources'] })} />
      </div>
    </div>
  )
}
