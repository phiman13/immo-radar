import { cn } from '../../lib/cn'

function scoreColor(score: number | null): string {
  if (score == null) return 'bg-[oklch(92%_0.005_240)] text-[oklch(40%_0.008_240)]'
  if (score >= 70) return 'bg-[oklch(88%_0.06_145)] text-[oklch(35%_0.13_145)]'
  if (score >= 50) return 'bg-[oklch(92%_0.06_75)] text-[oklch(38%_0.12_75)]'
  return 'bg-[oklch(93%_0.04_25)] text-[oklch(38%_0.14_25)]'
}

interface ScoreBadgeProps {
  score: number | null
  label?: string
  className?: string
}

export function ScoreBadge({ score, label = 'Lage', className }: ScoreBadgeProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center w-10 h-10 rounded-full text-xs font-medium font-mono',
        scoreColor(score),
        className,
      )}
    >
      <span className="font-bold text-sm leading-none">{score ?? '–'}</span>
      <span className="text-[9px] leading-none mt-0.5 opacity-70">{label}</span>
    </div>
  )
}
