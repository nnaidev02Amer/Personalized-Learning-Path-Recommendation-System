import { useState } from 'react'
import { CheckCircle2, ChevronDown, Circle, Compass, ListChecks, Pause, Play, RotateCcw } from 'lucide-react'
import { api } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { useStudent } from '../../context/StudentContext'
import { useToast } from '../../context/ToastContext'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import ProgressBar from '../ui/ProgressBar'
import StarRating from '../ui/StarRating'
import { ErrorState, Skeleton } from '../ui/States'
import { FORMAT_ICON, STATUS_META } from '../../utils/courseStatus'
import { formatDate } from '../../utils/format'

export default function EnrollmentCard({ enrollment, onUpdated, defaultOpen = false }) {
  const { refresh } = useStudent()
  const toast = useToast()
  const [open, setOpen] = useState(defaultOpen)
  const [busy, setBusy] = useState(null)
  const course = useApi(open ? () => api.courses.get(enrollment.course.id) : null, [open, enrollment.course.id])

  const e = enrollment
  const meta = STATUS_META[e.status]
  const FormatIcon = FORMAT_ICON[e.course.content_format]
  const done = new Set(e.completed_lesson_ids)
  const quiz = course.data?.quizzes?.[0]

  const act = async (key, fn, success) => {
    setBusy(key)
    try {
      const updated = await fn()
      onUpdated(updated)
      refresh()
      if (success) toast.success(...(typeof success === 'function' ? success(updated) : success))
    } catch (err) {
      toast.error('Action failed', err.message)
    } finally {
      setBusy(null)
    }
  }

  const completeLesson = (lesson) => act(`lesson-${lesson.id}`, () => api.enrollments.completeLesson(e.id, lesson.id),
    (u) => (u.status === 'completed'
      ? ['Course completed!', `You finished ${e.course.title}. Take the quiz and rate the course.`]
      : ['Lesson completed', lesson.title]))

  return (
    <article className="rounded-2xl border border-line bg-surface shadow-sm">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
        <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
          <FormatIcon className="size-6" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-ink">{e.course.title}</h3>
            <Badge tone={meta.tone} icon={meta.icon}>{meta.label}</Badge>
          </div>
          <p className="mt-0.5 text-xs text-ink-3">
            {e.course.code} · {e.course.topic} · <span className="text-ink-2">{e.course.difficulty}</span> ·
            {' '}{e.completed_lessons}/{e.total_lessons} lessons · enrolled {formatDate(e.enrolled_at)}
            {e.completed_at && ` · completed ${formatDate(e.completed_at)}`}
          </p>
          <div className="mt-3 max-w-md"><ProgressBar value={e.progress} size="sm" showValue={false} /></div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {e.status === 'active' && e.next_lesson && (
            <Button size="sm" icon={Play} loading={busy === `lesson-${e.next_lesson.id}`} onClick={() => completeLesson(e.next_lesson)}>
              Complete next lesson
            </Button>
          )}
          {e.status === 'completed' && (
            <StarRating value={e.rating || 0} label="Rate this course"
                        onChange={(rating) => act('rate', () => api.enrollments.update(e.id, { rating }), ['Thanks!', `You rated this course ${rating}/5.`])} />
          )}
          {e.status !== 'dropped' && (
            <Button size="sm" variant="secondary" icon={Compass} to={`/learning/${e.course.id}`}>Insights</Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open}
                  icon={ChevronDown} className={open ? '[&>svg]:rotate-180' : ''}>
            {open ? 'Hide' : 'Lessons'}
          </Button>
        </div>
      </div>

      {open && (
        <div className="border-t border-line px-5 py-4">
          {course.loading && <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>}
          {course.error && <ErrorState compact error={course.error} onRetry={course.reload} />}
          {course.data && (
            <>
              <ol className="divide-y divide-line rounded-xl border border-line">
                {course.data.lessons.map((lesson) => {
                  const isDone = done.has(lesson.id)
                  return (
                    <li key={lesson.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                      {isDone ? <CheckCircle2 className="size-5 shrink-0 text-good" aria-label="Completed" />
                        : <Circle className="size-5 shrink-0 text-ink-3" aria-label="Not completed" />}
                      <span className={`flex-1 ${isDone ? 'text-ink-3' : 'text-ink'}`}>{lesson.position}. {lesson.title}</span>
                      <span className="hidden text-xs text-ink-3 sm:inline">{lesson.duration_min} min</span>
                      {!isDone && e.status === 'active' && (
                        <Button size="sm" variant="secondary" loading={busy === `lesson-${lesson.id}`} onClick={() => completeLesson(lesson)}>
                          Mark complete
                        </Button>
                      )}
                    </li>
                  )
                })}
              </ol>
              <div className="mt-4 flex flex-wrap gap-2">
                {quiz && e.status !== 'dropped' && (
                  <Button size="sm" icon={ListChecks} to={`/quiz/${quiz.id}`}>Take quiz ({quiz.question_count} questions)</Button>
                )}
                {e.status === 'active' && (
                  <Button size="sm" variant="danger-outline" icon={Pause} loading={busy === 'drop'}
                          onClick={() => act('drop', () => api.enrollments.update(e.id, { status: 'dropped' }), ['Course paused', 'You can resume it any time.'])}>
                    Pause course
                  </Button>
                )}
                {e.status === 'dropped' && (
                  <Button size="sm" icon={RotateCcw} loading={busy === 'resume'}
                          onClick={() => act('resume', () => api.enrollments.update(e.id, { status: 'active' }), ['Course resumed', e.course.title])}>
                    Resume course
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </article>
  )
}

