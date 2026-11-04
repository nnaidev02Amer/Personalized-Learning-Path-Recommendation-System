import { useState } from 'react'
import { Activity, Gauge, ListChecks, TrendingDown, TrendingUp } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import PageHeader from '../components/ui/PageHeader'
import { Card, StatCard } from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import ProgressBar from '../components/ui/ProgressBar'
import { EmptyState, ErrorState, PageSkeleton } from '../components/ui/States'
import WeeklyActivityChart from '../components/charts/WeeklyActivityChart'
import ScoreTimelineChart from '../components/charts/ScoreTimelineChart'
import TopicScoresChart from '../components/charts/TopicScoresChart'
import { STATUS_META } from '../utils/courseStatus'
import { formatDate, formatMinutes, percent } from '../utils/format'

const RANGES = [4, 8, 12, 26]

export default function Analytics() {
  const { studentId, version } = useStudent()
  const [weeks, setWeeks] = useState(12)
  const progress = useApi(() => api.students.progress(studentId, weeks), [studentId, weeks, version])
  const attempts = useApi(() => api.students.attempts(studentId, 100), [studentId, version])

  if (!progress.data && progress.loading) return <PageSkeleton />
  if (progress.error && !progress.data) return <ErrorState error={progress.error} onRetry={progress.reload} />

  const p = progress.data
  const t = p.score_trend
  const totalMinutes = p.weekly_activity.reduce((sum, w) => sum + w.minutes, 0)
  const activeDays = p.weekly_activity.reduce((sum, w) => sum + w.active_days, 0)
  const improving = t.change != null && t.change >= 0

  const rangePicker = (
    <label className="flex items-center gap-2 text-xs text-ink-3">
      <span className="hidden sm:inline">Range</span>
      <select value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} aria-label="Time range"
              className="h-8 rounded-lg border border-line bg-surface px-2 text-xs text-ink">
        {RANGES.map((w) => <option key={w} value={w}>Last {w} weeks</option>)}
      </select>
    </label>
  )

  return (
    <div className="space-y-6">
      <PageHeader title="Progress & Analytics" description="Your completion, study activity and quiz performance over time." />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Gauge} label="Overall completion" value={percent(p.overall_completion)} hint="Lessons done across enrolled courses" />
        <StatCard icon={Activity} label={`Study time · ${weeks} weeks`} value={formatMinutes(totalMinutes)} hint={`${activeDays} active days`} tone="good" />
        <StatCard icon={ListChecks} label="Quiz attempts" value={t.attempts}
                  hint={t.second_half_average != null ? `Recent average ${t.second_half_average}%` : 'No attempts yet'} />
        <StatCard icon={improving ? TrendingUp : TrendingDown} label="Score change"
                  value={t.change == null ? '—' : `${t.change > 0 ? '+' : ''}${t.change} pts`}
                  hint={t.change == null ? 'Needs at least 2 quizzes' : `Earlier ${t.first_half_average}% → recent ${t.second_half_average}%`}
                  tone={t.change == null ? 'brand' : improving ? 'good' : 'critical'} />
      </div>

      <WeeklyActivityChart weeks={p.weekly_activity} subtitle={`Hours studied per week · last ${weeks} weeks`} action={rangePicker} height={280} />

      <div className="grid gap-6 lg:grid-cols-2">
        <ScoreTimelineChart points={p.quiz_scores}
                            subtitle={t.slope_per_week != null ? `Trend: ${t.slope_per_week > 0 ? '+' : ''}${t.slope_per_week} points per week (linear fit)` : 'All attempts'} />
        <TopicScoresChart data={p.scores_by_topic} subtitle="Across all quiz attempts" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Course progress" subtitle={`${p.courses.length} enrolment${p.courses.length === 1 ? '' : 's'}`}>
          {p.courses.length === 0 ? (
            <EmptyState title="No enrolments yet" message="Enroll in a course to track its progress here." />
          ) : (
            <ul className="space-y-4">
              {p.courses.map((c) => {
                const meta = STATUS_META[c.status]
                return (
                  <li key={c.enrollment_id}>
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="truncate text-sm text-ink">{c.course.title}</span>
                      <Badge tone={meta.tone} icon={meta.icon}>{meta.label}</Badge>
                    </div>
                    <ProgressBar value={c.progress} size="sm" tone={c.status === 'completed' ? 'good' : 'brand'} label={c.course.code} />
                  </li>
                )
              })}
            </ul>
          )}
        </Card>

        <Card title="Quiz history" subtitle="Most recent first">
          {attempts.error && <ErrorState compact error={attempts.error} onRetry={attempts.reload} />}
          {attempts.data?.length === 0 && <EmptyState icon={ListChecks} title="No quiz attempts yet" />}
          {attempts.data?.length > 0 && (
            <div className="max-h-96 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-surface text-xs text-ink-3">
                  <tr><th className="py-2 pr-3 font-medium">Date</th><th className="py-2 pr-3 font-medium">Course</th><th className="py-2 pr-3 text-right font-medium">Score</th><th className="py-2 font-medium">Result</th></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {attempts.data.map((a) => (
                    <tr key={a.id}>
                      <td className="whitespace-nowrap py-2.5 pr-3 text-ink-3">{formatDate(a.attempted_at)}</td>
                      <td className="py-2.5 pr-3 text-ink-2">{a.course_title}</td>
                      <td className="py-2.5 pr-3 text-right font-medium tabular-nums text-ink">
                        {a.score}%{a.total != null && <span className="ml-1 text-xs font-normal text-ink-3">({a.correct}/{a.total})</span>}
                      </td>
                      <td className="py-2.5"><Badge tone={a.passed ? 'good' : 'critical'}>{a.passed ? 'Passed' : 'Below pass'}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
