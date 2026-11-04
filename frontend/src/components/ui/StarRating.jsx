import { Star } from 'lucide-react'

export default function StarRating({ value = 0, onChange, size = 'md', label = 'Rating' }) {
  const cls = size === 'sm' ? 'size-3.5' : 'size-5'
  const interactive = Boolean(onChange)
  return (
    <div className="inline-flex items-center gap-0.5" role={interactive ? 'radiogroup' : 'img'}
         aria-label={interactive ? label : `${label}: ${value ? value.toFixed(1) : 'none'} of 5`}>
      {[1, 2, 3, 4, 5].map((n) => {
        const filled = value >= n - 0.25
        const star = <Star className={`${cls} ${filled ? 'fill-amber-400 text-amber-400' : 'text-ink-3/50'}`} aria-hidden />
        return interactive ? (
          <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? 's' : ''}`}
                  onClick={() => onChange(n)} className="rounded p-0.5 hover:scale-110 focus-visible:outline-2 focus-visible:outline-brand">
            {star}
          </button>
        ) : <span key={n}>{star}</span>
      })}
    </div>
  )
}
