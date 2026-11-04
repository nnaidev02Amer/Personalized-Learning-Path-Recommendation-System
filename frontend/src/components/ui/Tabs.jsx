export default function Tabs({ tabs, value, onChange, label = 'Tabs' }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex max-w-full gap-1 overflow-x-auto rounded-xl border border-line bg-surface p-1">
      {tabs.map((t) => {
        const active = t.value === value
        return (
          <button key={t.value} role="tab" aria-selected={active} onClick={() => onChange(t.value)}
                  className={`flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors
                    ${active ? 'bg-brand text-white' : 'text-ink-2 hover:bg-surface-2 hover:text-ink'}`}>
            {t.label}
            {t.count != null && (
              <span className={`rounded-full px-1.5 text-xs tabular-nums ${active ? 'bg-white/20' : 'bg-surface-2 text-ink-3'}`}>{t.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
