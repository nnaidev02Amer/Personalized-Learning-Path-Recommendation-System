import { useMemo, useState } from 'react'
import { Bot, Brain, Gauge, LineChart, Puzzle, Route, Sparkles, Target, TrendingDown } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import PageHeader from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import Badge, { DIFFICULTY_TONE } from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { EmptyState, ErrorState, Notice, PageSkeleton } from '../components/ui/States'
import CourseDetailModal from '../components/course/CourseDetailModal'
import { FORMAT_ICON, courseStatuses } from '../utils/courseStatus'

const PLANNED = [
  { icon: Brain, title: 'Learning-style prediction', text: 'Decision-tree model on your behaviour, shown next to your self-reported style.' },
  { icon: Sparkles, title: 'Hybrid course recommendations', text: 'Content-based + collaborative filtering over real enrolments and ratings.' },
  { icon: Puzzle, title: 'Skill-gap analysis', text: 'Per-skill mastery estimated from your quiz answers.' },
  { icon: Gauge, title: 'Adaptive difficulty', text: 'Suggested next difficulty level based on recent performance.' },
  { icon: LineChart, title: 'Performance prediction', text: 'Expected score on upcoming quizzes, with the model’s measured error.' },
  { icon: Bot, title: 'AI learning assistant', text: 'Answers grounded in your data; optional Claude API when a key is configured.' },
]

export default function Recommendations() {
  const { student, studentId, version, refresh } = useStudent()
  const [openId, setOpenId] = useState(null)
  const progress = useApi(() => api.students.progress(studentId, 12), [studentId, version])
  const courses = useApi(() => api.courses.list(), [])
  const enrollments = useApi(() => api.enrollments.list(studentId), [studentId, version])

  const statuses = useMemo(() => courseStatuses(courses.data?.items, enrollments.data), [courses.data, enrollments.data])

  if (!progress.data && progress.loading) return <PageSkeleton cards={2} />
  const error = progress.error || courses.error || enrollments.error
  if (error) return <ErrorState error={error} onRetry={() => { progress.reload(); courses.reload(); enrollments.reload() }} />

  const weakest = (progress.data?.scores_by_topic || []).slice(0, 3)
  const formatMatches = (courses.data?.items || [])
    .filter((c) => statuses.get(c.id)?.status === 'available' && c.content_format === student.preferred_content)
    .sort((a, b) => a.level - b.level || (b.average_rating || 0) - (a.average_rating || 0))
    .slice(0, 4)

  return (
    <div className="space-y-6">
      <PageHeader title="AI Recommendations" description="Personalised suggestions for what to learn next." />
      <Notice tone="warning" title="AI models are connected in Phase 5">
        No machine-learning output is shown on this page yet, and nothing here is simulated. The sections below are
        simple rules and statistics computed from your real data, and are labelled as such.
      </Notice>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Your learning profile" subtitle="From your student record">
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between gap-3"><dt className="text-ink-3">Learning style (self-reported)</dt><dd className="font-medium text-ink">{student.learning_style || 'Not set'}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-ink-3">Preferred format</dt><dd className="font-medium text-ink">{student.preferred_content}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-ink-3">ML-predicted style</dt><dd><Badge>Phase 5</Badge></dd></div>
          </dl>
          <Button to="/profile" variant="secondary" size="sm" className="mt-4">Edit profile</Button>
        </Card>

        <Card title="Topics to strengthen" subtitle="Lowest average quiz scores" action={<Badge>Descriptive statistics</Badge>}>
          {weakest.length === 0 ? (
            <EmptyState icon={Target} title="No quiz data yet" message="Take quizzes to see which topics need attention." />
          ) : (
            <ul className="space-y-3">
              {weakest.map((t) => (
                <li key={t.topic} className="flex items-center gap-3">
                  <TrendingDown className={`size-4 shrink-0 ${t.average_score < 60 ? 'text-critical' : 'text-warning'}`} aria-hidden />
                  <span className="flex-1 text-sm text-ink">{t.topic}</span>
                  <span className="text-sm font-medium tabular-nums text-ink-2">{t.average_score}%</span>
                  <span className="text-xs text-ink-3">({t.attempts})</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Matches your preferred format" subtitle={`Unlocked ${student.preferred_content.toLowerCase()} courses`} action={<Badge>Rule-based</Badge>}>
          {formatMatches.length === 0 ? (
            <EmptyState icon={Route} title="No matching courses unlocked" message="Complete prerequisites or browse other formats in the catalog." />
          ) : (
            <ul className="space-y-2">
              {formatMatches.map((c) => {
                const Icon = FORMAT_ICON[c.content_format]
                return (
                  <li key={c.id}>
                    <button onClick={() => setOpenId(c.id)} className="flex w-full items-center gap-3 rounded-lg border border-line p-3 text-left hover:bg-surface-2">
                      <Icon className="size-5 shrink-0 text-brand" aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink">{c.title}</span>
                        <span className="text-xs text-ink-3">{c.code} · {c.topic}</span>
                      </span>
                      <Badge tone={DIFFICULTY_TONE[c.difficulty]}>{c.difficulty}</Badge>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Coming in Phase 5" subtitle="AI features that will use the project's ML models and your real activity">
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PLANNED.map(({ icon: Icon, title, text }) => (
            <li key={title} className="rounded-xl border border-dashed border-line p-4">
              <div className="flex items-center gap-2">
                <Icon className="size-5 text-brand" aria-hidden />
                <span className="font-medium text-ink">{title}</span>
              </div>
              <p className="mt-1.5 text-sm text-ink-3">{text}</p>
              <Badge className="mt-3">Planned</Badge>
            </li>
          ))}
        </ul>
      </Card>

      <CourseDetailModal courseId={openId} status={openId ? statuses.get(openId) : null}
                         onClose={() => setOpenId(null)} onChanged={() => { enrollments.reload(); refresh() }} />
    </div>
  )
}
