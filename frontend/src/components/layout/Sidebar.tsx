import { NavLink } from 'react-router-dom'
import { House, Gear, ChartBar } from '@phosphor-icons/react'
import { cn } from '../../lib/cn'

const NAV = [
  { to: '/', icon: House, label: 'Listings' },
  { to: '/settings', icon: Gear, label: 'Einstellungen' },
  { to: '/system', icon: ChartBar, label: 'System' },
]

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-full w-[220px] border-r flex flex-col py-8 px-4 z-20"
      style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}>
      <div className="mb-10 px-2">
        <h1 className="font-display text-lg font-bold leading-tight" style={{ color: 'var(--fg)' }}>
          immo-radar
        </h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--muted)' }}>Tutzing · Starnberger See</p>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'text-white'
                  : 'hover:bg-[var(--accent-muted)]',
              )
            }
            style={({ isActive }) =>
              isActive ? { background: 'var(--accent)', color: 'white' } : { color: 'var(--fg)' }
            }
          >
            <Icon size={18} weight="regular" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
