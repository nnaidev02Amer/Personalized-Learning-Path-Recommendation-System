import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useChartColors } from '../../context/ThemeContext'
import { formatMinutes, shortDate } from '../../utils/format'
import ChartCard, { ChartTooltip } from './ChartCard'
import { EmptyState } from '../ui/States'

const COLUMNS = [
  { key: 'week_start', label: 'Week of', format: shortDate },
  { key: 'minutes', label: 'Study time', format: formatMinutes },
  { key: 'lessons', label: 'Lessons' },
  { key: 'quizzes', label: 'Quizzes' },
  { key: 'active_days', label: 'Active days' },
]

export default function WeeklyActivityChart({ weeks, title = 'Weekly study time', subtitle, action, height = 260 }) {
  const c = useChartColors()
  const empty = !weeks?.some((w) => w.minutes > 0)
  const data = (weeks || []).map((w) => ({ ...w, hours: Math.round((w.minutes / 60) * 10) / 10 }))
  return (
    <ChartCard title={title} subtitle={subtitle} columns={COLUMNS} rows={weeks} action={action}>
      {empty ? (
        <EmptyState title="No activity in this period" message="Complete a lesson or log study time to see your weekly activity." />
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={{ top: 8, right: 4, left: -12, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={c.grid} />
            <XAxis dataKey="week_start" tickFormatter={shortDate} tick={{ fill: c.axis, fontSize: 12 }}
                   axisLine={false} tickLine={false} minTickGap={8} />
            <YAxis tick={{ fill: c.axis, fontSize: 12 }} axisLine={false} tickLine={false}
                   tickFormatter={(v) => `${v}h`} width={44} allowDecimals />
            <Tooltip cursor={{ fill: c.grid, opacity: 0.5 }} content={(p) => (
              <ChartTooltip {...p} render={(d) => (
                <>
                  <p className="font-semibold text-ink">Week of {shortDate(d.week_start)}</p>
                  <p className="mt-1 text-ink-2">{formatMinutes(d.minutes)} studied</p>
                  <p className="text-ink-3">{d.lessons} lessons · {d.quizzes} quizzes · {d.active_days} active days</p>
                </>
              )} />
            )} />
            <Bar dataKey="hours" fill={c.series1} radius={[4, 4, 0, 0]} maxBarSize={40} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}
