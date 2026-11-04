export function Card({ title, subtitle, action, children, className = '', bodyClassName = '' }) {
  return (
    <section className={`rounded-2xl border border-line bg-surface shadow-sm ${className}`}>
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5">
          <div className="min-w-0">
            {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-ink-3">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={`p-5 ${bodyClassName}`}>{children}</div>
    </section>
  )
}

const TONES = {
  brand: 'bg-brand-soft text-brand',
  good: 'bg-good-soft text-good',
  warning: 'bg-warning-soft text-warning',
  critical: 'bg-critical-soft text-critical',
}

/** Single headline number with label and optional context line. */
export function StatCard({ icon: Icon, label, value, hint, tone = 'brand' }) {
  return (
    <div className="flex items-start gap-4 rounded-2xl border border-line bg-surface p-5 shadow-sm">
      {Icon && (
        <span className={`grid size-11 shrink-0 place-items-center rounded-xl ${TONES[tone]}`}>
          <Icon className="size-5" aria-hidden />
        </span>
      )}
      <div className="min-w-0">
        <p className="text-sm text-ink-3">{label}</p>
        <p className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</p>
        {hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
      </div>
    </div>
  )
}
