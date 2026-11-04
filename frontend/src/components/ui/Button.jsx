import { Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'

const VARIANTS = {
  primary: 'bg-brand text-white hover:bg-brand-strong dark:hover:text-bg',
  secondary: 'border border-line bg-surface text-ink hover:bg-surface-2',
  ghost: 'text-ink-2 hover:bg-surface-2 hover:text-ink',
  danger: 'bg-critical text-white hover:opacity-90',
  'danger-outline': 'border border-critical/40 text-critical hover:bg-critical-soft',
}
const SIZES = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-11 px-5 text-sm gap-2',
  icon: 'size-9 justify-center',
}

export function buttonClasses({ variant = 'primary', size = 'md', className = '' } = {}) {
  return `inline-flex shrink-0 items-center justify-center rounded-lg font-medium transition-colors
    focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand
    disabled:pointer-events-none disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`
}

export default function Button({ variant, size, icon: Icon, loading = false, className, children, to, ...props }) {
  const content = (
    <>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : Icon && <Icon className="size-4" aria-hidden />}
      {children}
    </>
  )
  const cls = buttonClasses({ variant, size, className })
  if (to) return <Link to={to} className={cls}>{content}</Link>
  return (
    <button type="button" className={cls} disabled={loading || props.disabled} {...props}>
      {content}
    </button>
  )
}
