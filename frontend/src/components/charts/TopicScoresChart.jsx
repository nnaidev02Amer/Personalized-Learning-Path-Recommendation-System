import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useChartColors } from '../../context/ThemeContext'
import ChartCard, { ChartTooltip } from './ChartCard'
import { EmptyState } from '../ui/States'

const COLUMNS = [
  { key: 'topic', label: 'Topic' },
  { key: 'average_score', label: 'Average score', format: (v) => `${v}%` },
  { key: 'attempts', label: 'Attempts' },
]

export default function TopicScoresChart({ data, title = 'Average score by topic', subtitle }) {
  const c = useChartColors()
  const rows = [...(data || [])].sort((a, b) => b.average_score - a.average_score)
  return (
    <ChartCard title={title} subtitle={subtitle} columns={COLUMNS} rows={rows}>
      {rows.length === 0 ? (
        <EmptyState title="No topic scores yet" message="Scores appear here once you have taken quizzes." />
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 44 + 30)}>
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, left: 0, bottom: 0 }}>
            <CartesianGrid horizontal={false} stroke={c.grid} />
            <XAxis type="number" domain={[0, 100]} tick={{ fill: c.axis, fontSize: 12 }} axisLine={false} tickLine={false}
                   tickFormatter={(v) => `${v}%`} />
            <YAxis type="category" dataKey="topic" width={128} tick={{ fill: c.axis, fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: c.grid, opacity: 0.5 }} content={(p) => (
              <ChartTooltip {...p} render={(d) => (
                <>
                  <p className="font-semibold text-ink">{d.topic}</p>
                  <p className="mt-0.5 text-ink-2">{d.average_score}% average · {d.attempts} attempt{d.attempts === 1 ? '' : 's'}</p>
                </>
              )} />
            )} />
            <Bar dataKey="average_score" fill={c.series1} radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false}>
              <LabelList dataKey="average_score" position="right" fill={c.axis} fontSize={12} formatter={(v) => `${Math.round(v)}%`} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}
