import { ChevronRight, Sparkles } from 'lucide-react'
import Badge, { DIFFICULTY_TONE } from '../ui/Badge'
import { EmptyState } from '../ui/States'
import { FORMAT_ICON } from '../../utils/courseStatus'

const LEVEL = { 1: 'Beginner', 2: 'Intermediate', 3: 'Advanced' }

export default function RecommendationList({ items, onOpen, compact = false }) {
  if (!items?.length) {
    return <EmptyState icon={Sparkles} title="No unlocked courses to recommend"
                       message="Finish your active courses to unlock new ones." />
  }
  return (
    <ol className={compact ? 'grid gap-3 md:grid-cols-3' : 'space-y-3'}>
      {items.map((r, i) => {
        const Icon = FORMAT_ICON[r.content_format]
        return (
          <li key={r.course_id}>
            <button onClick={() => onOpen(r.course_id)}
                    className="flex h-full w-full items-start gap-3 rounded-xl border border-line p-4 text-left transition hover:border-brand/40 hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-brand">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand-soft text-sm font-semibold text-brand">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-ink">{r.title}</span>
                  {!compact && <Badge tone={DIFFICULTY_TONE[LEVEL[r.difficulty_level]]}>{LEVEL[r.difficulty_level]}</Badge>}
                </span>
                <span className="mt-0.5 flex items-center gap-1 text-xs text-ink-3">
                  <Icon className="size-3.5" aria-hidden />{r.code} · {r.topic} · {r.content_format}
                </span>
                <ul className="mt-2 space-y-0.5 text-xs text-ink-2">
                  {r.reasons.slice(0, compact ? 1 : 3).map((reason) => <li key={reason}>• {reason}</li>)}
                </ul>
                {!compact && (
                  <span className="mt-2 flex gap-4 text-xs text-ink-3 tabular-nums">
                    <span>Collaborative {Math.round(r.collaborative_score * 100)}%</span>
                    <span>Content {Math.round(r.content_score * 100)}%</span>
                  </span>
                )}
              </span>
              <ChevronRight className="mt-1 size-4 shrink-0 text-ink-3" aria-hidden />
            </button>
          </li>
        )
      })}
    </ol>
  )
}
