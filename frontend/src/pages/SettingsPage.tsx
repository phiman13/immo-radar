import { useState } from 'react'
import { SearchProfileTab } from '../components/settings/SearchProfileTab'
import { NotificationsTab } from '../components/settings/NotificationsTab'
import { MechanicsTab } from '../components/settings/MechanicsTab'
import { SourcesTab } from '../components/settings/SourcesTab'
import { cn } from '../lib/cn'

const TABS = [
  { id: 'search', label: 'Suchprofil', component: SearchProfileTab },
  { id: 'notifications', label: 'Benachrichtigungen', component: NotificationsTab },
  { id: 'mechanics', label: 'Mechanik', component: MechanicsTab },
  { id: 'sources', label: 'Quellen', component: SourcesTab },
]

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState('search')
  const ActiveComponent = TABS.find((t) => t.id === activeTab)?.component ?? SearchProfileTab

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <h1 className="font-display text-2xl font-bold mb-6" style={{ color: 'var(--fg)' }}>
        Einstellungen
      </h1>

      {/* Tab nav */}
      <div className="flex gap-1 border-b mb-6" style={{ borderColor: 'var(--border)' }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors',
              activeTab === tab.id
                ? 'border-[var(--accent)]'
                : 'border-transparent hover:border-[var(--border)]',
            )}
            style={{ color: activeTab === tab.id ? 'var(--accent)' : 'var(--muted)' }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <ActiveComponent />
    </div>
  )
}
