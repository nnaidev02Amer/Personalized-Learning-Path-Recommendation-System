const TONES = {
  neutral: 'bg-surface-2 text-ink-2 border-line',
  brand: 'bg-brand-soft text-brand border-transparent',
  good: 'bg-good-soft text-good border-transparent',
  warning: 'bg-warning-soft text-warning border-transparent',
  critical: 'bg-critical-soft text-critical border-transparent',
}

export default function Badge({ tone = 'neutral', icon: Icon, children, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}>
      {Icon && <Icon className="size-3.5" aria-hidden />}
      {children}
    </span>
  )
}

export const DIFFICULTY_TONE = { Beginner: 'good', Intermediate: 'brand', Advanced: 'warning' }
