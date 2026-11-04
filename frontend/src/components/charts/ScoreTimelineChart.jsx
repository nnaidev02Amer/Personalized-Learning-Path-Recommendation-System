import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useChartColors } from '../../context/ThemeContext'
import { formatDate, shortDate } from '../../utils/format'
import ChartCard, { ChartTooltip } from './ChartCard'
import { EmptyState } from '../ui/States'

const PASS_MARK = 60
const COLUMNS = [
  { key: 'attempted_at', label: 'Date', format: (v) => formatDate(v) },
  { key: 'course_title', label: 'Course' },
  { key: 'score', label: 'Score', format: (v) => `${v}%` },
]

export default function ScoreTimelineChart({ points, title = 'Quiz scores over time', subtitle }) {
  const c = useChartColors()
  const data = (points || []).map((p, i) => ({ ...p, n: i + 1 }))
  return (
    <ChartCard title={title} subtitle={subtitle} columns={COLUMNS} rows={data}>
      {data.length === 0 ? (
        <EmptyState title="No quiz attempts yet" message="Take a course quiz to start tracking your scores." />
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={c.grid} />
            <XAxis dataKey="n" tickFormatter={(n) => shortDate(data[n - 1]?.attempted_at)} tick={{ fill: c.axis, fontSize: 12 }}
                   axisLine={false} tickLine={false} minTickGap={16} />
            <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: c.axis, fontSize: 12 }}
                   axisLine={false} tickLine={false} width={48} tickFormatter={(v) => `${v}%`} />
            <ReferenceLine y={PASS_MARK} stroke={c.axis} strokeDasharray="4 4"
                           label={{ value: 'Pass mark', position: 'insideBottomRight', fill: c.axis, fontSize: 11 }} />
            <Tooltip cursor={{ stroke: c.axis, strokeDasharray: '3 3' }} content={(p) => (
              <ChartTooltip {...p} render={(d) => (
                <>
                  <p className="font-semibold text-ink">{d.score}% · {d.course_title}</p>
                  <p className="mt-0.5 text-ink-3">{d.topic} · {formatDate(d.attempted_at)}</p>
                </>
              )} />
            )} />
            <Line type="monotone" dataKey="score" stroke={c.series1} strokeWidth={2}
                  dot={{ r: 4, fill: c.series1, stroke: c.surface, strokeWidth: 2 }}
                  activeDot={{ r: 6, fill: c.series1, stroke: c.surface, strokeWidth: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}
