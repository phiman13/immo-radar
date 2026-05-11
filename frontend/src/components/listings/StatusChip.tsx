import { cn } from '../../lib/cn'
import { STATUS_LABELS } from '../../types'

const STATUS_STYLES: Record<string, string> = {
  new: 'bg-[oklch(92%_0.04_145)] text-[oklch(35%_0.13_145)]',
  interessant: 'bg-[oklch(92%_0.04_145)] text-[oklch(35%_0.13_145)]',
  vielleicht: 'bg-[oklch(94%_0.05_75)] text-[oklch(40%_0.12_75)]',
  gesehen: 'bg-[oklch(92%_0.005_240)] text-[oklch(40%_0.008_240)]',
  abgelehnt: 'bg-[oklch(94%_0.04_25)] text-[oklch(38%_0.14_25)]',
}

interface StatusChipProps {
  status: string
  className?: string
}

export function StatusChip({ status, className }: StatusChipProps) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.gesehen
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium',
        style,
        className,
      )}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}
