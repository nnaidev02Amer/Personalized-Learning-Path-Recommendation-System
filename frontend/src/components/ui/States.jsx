import { AlertTriangle, Info, Inbox, RefreshCw, WifiOff } from 'lucide-react'
import Button from './Button'

export function Skeleton({ className = '' }) {
  return <div className={`skeleton rounded-lg ${className}`} aria-hidden />
}

/** Placeholder layout shown while a page's data loads. */
export function PageSkeleton({ cards = 4 }) {
  return (
    <div className="space-y-6" role="status" aria-label="Loading">
      <Skeleton className="h-28 w-full rounded-2xl" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: cards }).map((_, i) => <Skeleton key={i} className="h-24 rounded-2xl" />)}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-72 rounded-2xl lg:col-span-2" />
        <Skeleton className="h-72 rounded-2xl" />
      </div>
    </div>
  )
}

export function ErrorState({ error, onRetry, title = 'Something went wrong', compact = false }) {
  const offline = error?.code === 'network_error'
  const Icon = offline ? WifiOff : AlertTriangle
  return (
    <div role="alert" className={`flex flex-col items-center text-center ${compact ? 'py-6' : 'rounded-2xl border border-line bg-surface px-6 py-12'}`}>
      <span className="grid size-12 place-items-center rounded-full bg-critical-soft text-critical">
        <Icon className="size-6" aria-hidden />
      </span>
      <h3 className="mt-4 text-base font-semibold text-ink">{offline ? 'Backend not reachable' : title}</h3>
      <p className="mt-1 max-w-md text-sm text-ink-2">{error?.message || 'Please try again.'}</p>
      {offline && (
        <code className="mt-3 rounded-lg bg-surface-2 px-3 py-1.5 text-xs text-ink-2">
          python -m uvicorn backend.app.main:app --reload
        </code>
      )}
      {onRetry && <Button className="mt-5" variant="secondary" icon={RefreshCw} onClick={onRetry}>Try again</Button>}
    </div>
  )
}

export function EmptyState({ icon: Icon = Inbox, title, message, action }) {
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-surface-2 text-ink-3">
        <Icon className="size-6" aria-hidden />
      </span>
      <h3 className="mt-4 text-sm font-semibold text-ink">{title}</h3>
      {message && <p className="mt-1 max-w-sm text-sm text-ink-3">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

/** Inline information banner (used to label rule-based / upcoming features honestly). */
export function Notice({ icon: Icon = Info, title, children, tone = 'brand' }) {
  const tones = {
    brand: 'border-brand/30 bg-brand-soft text-brand',
    warning: 'border-warning/30 bg-warning-soft text-warning',
  }
  return (
    <div className={`flex gap-3 rounded-xl border px-4 py-3 ${tones[tone]}`}>
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="text-sm">
        {title && <p className="font-semibold">{title}</p>}
        <div className="text-ink-2">{children}</div>
      </div>
    </div>
  )
}
