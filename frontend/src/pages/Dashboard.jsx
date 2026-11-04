import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Award, BookOpenCheck, CalendarDays, Clock, Flame, Library, ListChecks, Target } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import { useToast } from '../context/ToastContext'
import { Card, StatCard } from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import ProgressBar from '../components/ui/ProgressBar'
import { EmptyState, ErrorState, PageSkeleton } from '../components/ui/States'
import WeeklyActivityChart from '../components/charts/WeeklyActivityChart'
import { FORMAT_ICON } from '../utils/courseStatus'
import { firstName, formatDate, formatMinutes, greeting, percent, relativeDay, score } from '../utils/format'

function ContinueLearning({ enrollments, onUpdated }) {
  const toast = useToast()
  const { refresh } = useStudent()
  const [busy, setBusy] = useState(null)
  const active = enrollments.filter((e) => e.status === 'active')

  const complete = async (e) => {
    setBusy(e.id)
    try {
      const updated = await api.enrollments.completeLesson(e.id, e.next_lesson.id)
      onUpdated(updated)
      refresh()
      toast.success(updated.status === 'completed' ? 'Course completed!' : 'Lesson completed', e.next_lesson.title)
    } catch (err) {
      toast.error('Could not complete lesson', err.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card title="Continue learning" subtitle={`${active.length} active course${active.length === 1 ? '' : 's'}`}
          action={<Link to="/learning" className="text-sm font-medium text-brand hover:underline">View all</Link>}
          className="lg:col-span-2">
      {active.length === 0 ? (
        <EmptyState icon={Library} title="No active courses" message="Pick your next course from the catalog."
                    action={<Button to="/courses" icon={Library}>Browse courses</Button>} />
      ) : (
        <ul className="space-y-4">
          {active.slice(0, 4).map((e) => {
            const Icon = FORMAT_ICON[e.course.content_format]
            return (
              <li key={e.id} className="flex flex-col gap-3 rounded-xl border border-line p-4 sm:flex-row sm:items-center">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand"><Icon className="size-5" aria-hidden /></span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-ink">{e.course.title}</p>
                  <p className="truncate text-xs text-ink-3">
                    {e.next_lesson ? `Next: ${e.next_lesson.position}. ${e.next_lesson.title} · ${e.next_lesson.duration_min} min` : 'All lessons done'}
                  </p>
                  <div className="mt-2"><ProgressBar value={e.progress} size="sm" label={`${e.completed_lessons}/${e.total_lessons} lessons`} /></div>
                </div>
                {e.next_lesson && (
                  <Button size="sm" variant="secondary" loading={busy === e.id} onClick={() => complete(e)}>Mark lesson done</Button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

export default function Dashboard() {
  const { student, version } = useStudent()
  const id = student.id
  const summary = useApi(() => api.students.summary(id), [id, version])
  const progress = useApi(() => api.students.progress(id, 8), [id, version])
  const enrollments = useApi(() => api.enrollments.list(id), [id])

  const loading = summary.loading && !summary.data
  const error = summary.error || progress.error || enrollments.error
  if (loading) return <PageSkeleton />
  if (error && !summary.data) return <ErrorState error={error} onRetry={() => { summary.reload(); progress.reload(); enrollments.reload() }} />

  const s = summary.data
  const weekGoal = s.daily_goal_minutes * 7
  const recent = [...(progress.data?.quiz_scores || [])].reverse().slice(0, 5)
  const updateEnrollment = (u) => enrollments.setData((list) => list.map((e) => (e.id === u.id ? u : e)))

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <section className="relative overflow-hidden rounded-2xl border border-line bg-surface p-6 shadow-sm sm:p-8">
        <div className="pointer-events-none absolute -right-16 -top-16 size-64 rounded-full bg-brand-soft" aria-hidden />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm text-ink-3">{formatDate(new Date(), { weekday: 'long', day: 'numeric', month: 'long' })}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
              {greeting()}, {firstName(student.name)}
            </h1>
            <p className="mt-2 max-w-xl text-sm text-ink-2">
              You have {s.lessons_pending} lesson{s.lessons_pending === 1 ? '' : 's'} left in your active courses
              and studied {formatMinutes(s.minutes_last_7_days)} in the last 7 days. Last active {relativeDay(s.last_active)}.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {student.learning_style && <Badge tone="brand">{student.learning_style} learner</Badge>}
              <Badge>Prefers {student.preferred_content.toLowerCase()}</Badge>
              <Badge>Goal {formatMinutes(student.daily_goal_minutes)}/day</Badge>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button to="/learning" icon={ArrowRight}>Continue learning</Button>
            <Button to="/courses" variant="secondary" icon={Library}>Explore courses</Button>
          </div>
        </div>
      </section>

      {/* Key numbers */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Award} label="Courses completed" value={s.completed_courses}
                  hint={`${s.active_courses} in progress${s.dropped_courses ? ` · ${s.dropped_courses} paused` : ''}`} tone="good" />
        <StatCard icon={ListChecks} label="Average quiz score" value={score(s.average_quiz_score)}
                  hint={`${s.quizzes_taken} quiz${s.quizzes_taken === 1 ? '' : 'zes'} taken`} />
        <StatCard icon={Clock} label="Study time · last 7 days" value={formatMinutes(s.minutes_last_7_days)}
                  hint={`${percent(Math.min(s.minutes_last_7_days / weekGoal, 9.99))} of weekly goal (${formatMinutes(weekGoal)})`}
                  tone={s.minutes_last_7_days >= weekGoal ? 'good' : 'warning'} />
        <StatCard icon={Flame} label="Current streak" value={`${s.current_streak_days} day${s.current_streak_days === 1 ? '' : 's'}`}
                  hint={`Last active ${relativeDay(s.last_active)}`} tone={s.current_streak_days ? 'good' : 'warning'} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {enrollments.data
          ? <ContinueLearning enrollments={enrollments.data} onUpdated={updateEnrollment} />
          : <Card title="Continue learning" className="lg:col-span-2"><ErrorState compact error={enrollments.error} onRetry={enrollments.reload} /></Card>}

        <Card title="Lessons" subtitle="Across all enrolled courses">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-good-soft p-4">
              <BookOpenCheck className="size-5 text-good" aria-hidden />
              <p className="mt-2 text-2xl font-semibold text-ink tabular-nums">{s.lessons_completed}</p>
              <p className="text-xs text-ink-3">completed</p>
            </div>
            <div className="rounded-xl bg-warning-soft p-4">
              <Target className="size-5 text-warning" aria-hidden />
              <p className="mt-2 text-2xl font-semibold text-ink tabular-nums">{s.lessons_pending}</p>
              <p className="text-xs text-ink-3">pending</p>
            </div>
          </div>
          {progress.data && (
            <div className="mt-5"><ProgressBar value={progress.data.overall_completion} label="Overall completion" /></div>
          )}
          <div className="mt-5 flex items-center gap-2 text-sm text-ink-3">
            <CalendarDays className="size-4" aria-hidden /> {formatMinutes(s.minutes_total)} studied in total
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {progress.data
            ? <WeeklyActivityChart weeks={progress.data.weekly_activity} subtitle="Last 8 weeks" />
            : <Card title="Weekly study time"><ErrorState compact error={progress.error} onRetry={progress.reload} /></Card>}
        </div>
        <Card title="Recent quiz results" action={<Link to="/analytics" className="text-sm font-medium text-brand hover:underline">Analytics</Link>}>
          {recent.length === 0 ? (
            <EmptyState icon={ListChecks} title="No quizzes yet" message="Complete lessons, then take the course quiz." />
          ) : (
            <ul className="divide-y divide-line">
              {recent.map((q, i) => (
                <li key={i} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink">{q.course_title}</p>
                    <p className="text-xs text-ink-3">{formatDate(q.attempted_at)}</p>
                  </div>
                  <Badge tone={q.score >= 60 ? 'good' : 'critical'}>{q.score >= 60 ? 'Passed' : 'Below pass'} · {Math.round(q.score)}%</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
