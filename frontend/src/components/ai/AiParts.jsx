import { Cpu, Database } from 'lucide-react'
import Badge from '../ui/Badge'

/** Marks content as a real model output, and whether the student's history is synthetic. */
export function ModelBadge({ data, label = 'ML model output' }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge tone="brand" icon={Cpu}>{label}</Badge>
      {data?.student_history?.startsWith('synthetic') && (
        <Badge tone="warning" icon={Database}>Synthetic history</Badge>
      )}
    </div>
  )
}

/** Horizontal meter with a visible numeric label (identity never relies on colour alone). */
export function Meter({ label, value, sublabel, tone = 'brand' }) {
  const pct = Math.max(0, Math.min(1, value ?? 0)) * 100
  const fill = { brand: 'bg-brand', good: 'bg-good', warning: 'bg-warning', critical: 'bg-critical' }[tone]
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
        <span className="truncate text-ink">{label}</span>
        <span className="shrink-0 tabular-nums font-medium text-ink-2">{Math.round(pct)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-2" role="meter" aria-valuenow={Math.round(pct)}
           aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className={`h-2 rounded-full ${fill}`} style={{ width: `${pct}%` }} />
      </div>
      {sublabel && <p className="mt-1 text-xs text-ink-3">{sublabel}</p>}
    </div>
  )
}

export const masteryTone = (m) => (m >= 0.6 ? 'good' : m >= 0.4 ? 'warning' : 'critical')

/** Small "evaluated vs baseline" footnote used under each model card. */
export function EvalNote({ children }) {
  return <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-ink-3">{children}</p>
}
