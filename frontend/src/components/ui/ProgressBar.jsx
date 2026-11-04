export default function ProgressBar({ value = 0, label, showValue = true, size = 'md', tone = 'brand' }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  const height = size === 'sm' ? 'h-1.5' : 'h-2'
  const fill = tone === 'good' ? 'bg-good' : 'bg-brand'
  return (
    <div>
      {(label || showValue) && (
        <div className="mb-1.5 flex justify-between text-xs text-ink-3">
          <span>{label}</span>
          {showValue && <span className="tabular-nums font-medium text-ink-2">{Math.round(pct)}%</span>}
        </div>
      )}
      <div className={`${height} overflow-hidden rounded-full bg-surface-2`} role="progressbar"
           aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label || 'Progress'}>
        <div className={`${height} rounded-full ${fill} transition-[width] duration-500`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
