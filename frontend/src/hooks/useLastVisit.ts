import { useEffect, useRef } from 'react'

const KEY = 'immo_radar_last_visit'

export function useLastVisit(): Date {
  const lastVisit = useRef<Date>(
    new Date(localStorage.getItem(KEY) ?? '1970-01-01'),
  )

  useEffect(() => {
    const timer = setTimeout(() => {
      localStorage.setItem(KEY, new Date().toISOString())
    }, 5_000)
    return () => clearTimeout(timer)
  }, [])

  return lastVisit.current
}

export function isNewSinceLastVisit(firstSeenAt: string, lastVisit: Date): boolean {
  return new Date(firstSeenAt) > lastVisit
}
