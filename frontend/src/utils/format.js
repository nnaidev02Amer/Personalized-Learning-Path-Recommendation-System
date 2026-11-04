export function formatMinutes(min) {
  if (min == null) return '—'
  const m = Math.round(min)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r ? `${h}h ${r}m` : `${h}h`
}

export function formatDate(value, opts = { day: 'numeric', month: 'short', year: 'numeric' }) {
  if (!value) return '—'
  const d = typeof value === 'string' && value.length === 10 ? new Date(`${value}T00:00:00`) : new Date(value)
  return d.toLocaleDateString(undefined, opts)
}

export const shortDate = (v) => formatDate(v, { day: 'numeric', month: 'short' })

export function percent(value, digits = 0) {
  if (value == null) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function score(value) {
  return value == null ? '—' : `${Math.round(value)}%`
}

export function relativeDay(value) {
  if (!value) return 'never'
  const d = new Date(`${value}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((today - d) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}

export function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export function firstName(name = '') {
  return name.split(' ')[0] || name
}

export function initials(name = '') {
  return name.split(' ').filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('')
}
