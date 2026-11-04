import { useState } from 'react'
import { BarChart3, Table2 } from 'lucide-react'
import { Card } from '../ui/Card'

/** Card wrapper giving every chart an accessible table view. */
export default function ChartCard({ title, subtitle, columns, rows, children, action, className = '' }) {
  const [asTable, setAsTable] = useState(false)
  const toggle = (
    <div className="flex items-center gap-2">
      {action}
      {rows?.length > 0 && (
        <button onClick={() => setAsTable((t) => !t)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-surface-2"
                aria-pressed={asTable}>
          {asTable ? <BarChart3 className="size-3.5" aria-hidden /> : <Table2 className="size-3.5" aria-hidden />}
          {asTable ? 'Chart' : 'Table'}
        </button>
      )}
    </div>
  )
  return (
    <Card title={title} subtitle={subtitle} action={toggle} className={className}>
      {asTable ? (
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-surface text-xs text-ink-3">
              <tr>{columns.map((c) => <th key={c.key} className="py-2 pr-4 font-medium">{c.label}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r, i) => (
                <tr key={i}>{columns.map((c) => <td key={c.key} className="py-2 pr-4 text-ink-2 tabular-nums">{c.format ? c.format(r[c.key], r) : r[c.key]}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : children}
    </Card>
  )
}

export function ChartTooltip({ active, payload, render }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      {render(payload[0].payload)}
    </div>
  )
}
