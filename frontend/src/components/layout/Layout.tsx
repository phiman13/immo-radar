import type { ReactNode } from 'react'
import { Sidebar } from './Sidebar'

interface LayoutProps {
  children: ReactNode
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-[100dvh] flex" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <main className="ml-[220px] flex-1 min-w-0">
        {children}
      </main>
    </div>
  )
}
