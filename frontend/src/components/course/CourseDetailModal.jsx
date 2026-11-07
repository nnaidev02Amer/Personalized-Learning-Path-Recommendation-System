import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Circle, Clock, Hourglass, ListChecks, Lock, PlayCircle, RotateCcw, Send, XCircle } from 'lucide-react'
import { api } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { useStudent } from '../../context/StudentContext'
import { useToast } from '../../context/ToastContext'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import Badge, { DIFFICULTY_TONE } from '../ui/Badge'
import { ErrorState, Skeleton } from '../ui/States'
import { FORMAT_ICON, STATUS_META } from '../../utils/courseStatus'

export default function CourseDetailModal({ courseId, status, onClose, onChanged }) {
  const { studentId, refresh } = useStudent()
  const toast = useToast()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [blocked, setBlocked] = useState(null)
  const current = status?.status
  const { data: course, error, loading, reload } = useApi(courseId ? () => api.courses.get(courseId) : null, [courseId])

  const enroll = async () => {
    setBusy(true)
    setBlocked(null)
    try {
      if (current === 'dropped') await api.enrollments.update(status.enrollment.id, { status: 'active' })
      else if (course.is_locked) await api.enrollmentRequests.create(studentId, courseId)
      else await api.enrollments.create(studentId, courseId)
      if (current === 'dropped') toast.success('Course resumed', `You can continue ${course.title}.`)
      else if (course.is_locked) toast.success('Request sent', `An administrator will review your request for ${course.title}.`)
      else toast.success('Enrolled', `You are now enrolled in ${course.title}.`)
      refresh()
      onChanged?.()
    } catch (e) {
      if (e.code === 'prerequisites_not_met') setBlocked(e)
      else toast.error(course.is_locked ? 'Could not send the request' : 'Could not enroll', e.message)
    } finally {
      setBusy(false)
    }
  }

  const cancelRequest = async () => {
    setBusy(true)
    try {
      await api.enrollmentRequests.cancel(studentId, status.request.id)
      toast.success('Request withdrawn', `Your request for ${course.title} was cancelled.`)
      onChanged?.()
    } catch (e) {
      toast.error('Could not withdraw the request', e.message)
    } finally {
      setBusy(false)
    }
  }

  const meta = STATUS_META[current || 'available']
  const done = new Set(status?.enrollment?.completed_lesson_ids || [])
  const FormatIcon = course ? FORMAT_ICON[course.content_format] : null

  let footer = null
  if (course) {
    if (current === 'active' || current === 'completed') {
      footer = <Button icon={ArrowRight} onClick={() => navigate('/learning')}>{current === 'completed' ? 'Review in My Learning' : 'Start learning'}</Button>
    } else if (current === 'dropped') {
      footer = <Button icon={RotateCcw} loading={busy} onClick={enroll}>Resume course</Button>
    } else if (current === 'pending') {
      footer = <Button variant="secondary" icon={XCircle} loading={busy} onClick={cancelRequest}>Withdraw request</Button>
    } else {
      footer = course.is_locked
        ? <Button icon={Send} loading={busy} onClick={enroll} disabled={current === 'locked'}>Request access</Button>
        : <Button icon={PlayCircle} loading={busy} onClick={enroll} disabled={current === 'locked'}>Enroll</Button>
    }
  }

  return (
    <Modal open={Boolean(courseId)} onClose={onClose} title={course ? `${course.code} · ${course.title}` : 'Course'} size="lg"
           footer={footer && <><Button variant="secondary" onClick={onClose}>Close</Button>{footer}</>}>
      {loading && <div className="space-y-3"><Skeleton className="h-6 w-1/2" /><Skeleton className="h-20" /><Skeleton className="h-40" /></div>}
      {error && <ErrorState compact error={error} onRetry={reload} />}
      {course && (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-2">
            <Badge tone={meta.tone} icon={meta.icon}>{meta.label}</Badge>
            <Badge tone={DIFFICULTY_TONE[course.difficulty]}>{course.difficulty}</Badge>
            <Badge icon={FormatIcon}>{course.content_format}</Badge>
            <Badge icon={Clock}>{course.duration_hours} hours</Badge>
            <Badge>{course.topic}</Badge>
          </div>
          <p className="text-sm leading-relaxed text-ink-2">{course.description}</p>

          {course.is_locked && current !== 'pending' && !status?.enrollment && (
            <p className="flex items-center gap-2 rounded-xl bg-surface-2 px-4 py-3 text-sm text-ink-2">
              <Lock className="size-4 shrink-0 text-warning" aria-hidden />This course is locked: send an access request and an administrator will review it.
            </p>
          )}
          {current === 'pending' && (
            <div className="rounded-xl border border-warning/30 bg-warning-soft p-4 text-sm">
              <p className="flex items-center gap-2 font-semibold text-warning"><Hourglass className="size-4" aria-hidden />Waiting for approval</p>
              <p className="mt-1 text-ink-2">An administrator must approve your request before you can study this course.</p>
            </div>
          )}
          {current !== 'pending' && status?.rejected && !status?.enrollment && (
            <div className="rounded-xl border border-critical/30 bg-critical-soft p-4 text-sm">
              <p className="font-semibold text-critical">Your last request was declined</p>
              {status.rejected.note && <p className="mt-1 text-ink-2">Reason: {status.rejected.note}</p>}
              <p className="mt-1 text-ink-2">You can send a new request.</p>
            </div>
          )}

          {(blocked || current === 'locked') && (
            <div className="rounded-xl border border-warning/30 bg-warning-soft p-4 text-sm">
              <p className="flex items-center gap-2 font-semibold text-warning"><Lock className="size-4" aria-hidden />Prerequisites required</p>
              <p className="mt-1 text-ink-2">Complete these courses first: {(blocked?.details?.map((d) => `${d.code} ${d.title}`) || status?.missing || []).join(', ')}</p>
            </div>
          )}

          <div>
            <h3 className="text-sm font-semibold text-ink">Skills you will practise</h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {course.skills.map((s) => <Badge key={s} tone="brand">{s.replace(/-/g, ' ')}</Badge>)}
            </div>
          </div>

          {course.prerequisites.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-ink">Prerequisites</h3>
              <ul className="mt-2 flex flex-wrap gap-2 text-sm">
                {course.prerequisites.map((p) => {
                  const missing = status?.missing?.includes(p.code)
                  return (
                    <li key={p.id} className={`flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 ${missing ? 'text-warning' : 'text-good'}`}>
                      {missing ? <Lock className="size-3.5" aria-hidden /> : <CheckCircle2 className="size-3.5" aria-hidden />}
                      <span className="text-ink-2">{p.code} · {p.title}</span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          <div>
            <h3 className="text-sm font-semibold text-ink">Lessons ({course.lessons.length})</h3>
            <ol className="mt-2 divide-y divide-line rounded-xl border border-line">
              {course.lessons.map((l) => (
                <li key={l.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                  {done.has(l.id) ? <CheckCircle2 className="size-4 shrink-0 text-good" aria-label="Completed" />
                    : <Circle className="size-4 shrink-0 text-ink-3" aria-hidden />}
                  <span className="flex-1 text-ink-2">{l.position}. {l.title}</span>
                  <span className="text-xs text-ink-3">{l.duration_min} min</span>
                </li>
              ))}
            </ol>
          </div>

          {course.quizzes.map((q) => (
            <div key={q.id} className="flex items-center gap-3 rounded-xl bg-surface-2 px-4 py-3 text-sm">
              <ListChecks className="size-5 text-brand" aria-hidden />
              <span className="flex-1 text-ink-2">{q.title} · {q.question_count} questions · pass mark {q.pass_score}%</span>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
