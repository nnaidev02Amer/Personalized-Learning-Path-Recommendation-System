import { useMemo, useState } from 'react'
import { ChevronRight, Map as MapIcon } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import PageHeader from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import ProgressBar from '../components/ui/ProgressBar'
import { EmptyState, ErrorState, Notice, PageSkeleton } from '../components/ui/States'
import CourseDetailModal from '../components/course/CourseDetailModal'
import { STATUS_META, courseStatuses } from '../utils/courseStatus'

const NODE_STYLE = {
  completed: 'border-good/40 bg-good-soft',
  active: 'border-brand bg-brand-soft ring-2 ring-brand/20',
  dropped: 'border-line bg-surface-2',
  available: 'border-line bg-surface',
  locked: 'border-dashed border-line bg-surface opacity-70',
}

const TONE_TEXT = { good: 'text-good', brand: 'text-brand', warning: 'text-warning', neutral: 'text-ink-3' }

function Node({ course, status, onOpen }) {
  const meta = STATUS_META[status.status]
  const Icon = meta.icon
  return (
    <button onClick={() => onOpen(course.id)}
            className={`h-full w-full rounded-xl border p-3 text-left transition hover:shadow-md focus-visible:outline-2 focus-visible:outline-brand ${NODE_STYLE[status.status]}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-ink-3">{course.code} · L{course.level}</span>
        <span className={`flex items-center gap-1 text-xs font-medium ${TONE_TEXT[meta.tone]}`}>
          <Icon className="size-3.5" aria-hidden />{meta.label}
        </span>
      </div>
      <p className="mt-1 line-clamp-2 text-sm font-medium text-ink">{course.title}</p>
      {status.status === 'active' && status.enrollment && (
        <div className="mt-2"><ProgressBar value={status.enrollment.progress} size="sm" showValue={false} /></div>
      )}
      {status.status === 'locked' && <p className="mt-1 text-xs text-ink-3">Needs {status.missing.join(', ')}</p>}
    </button>
  )
}

export default function Roadmap() {
  const { studentId, refresh } = useStudent()
  const [openId, setOpenId] = useState(null)
  const courses = useApi(() => api.courses.list(), [])
  const enrollments = useApi(() => api.enrollments.list(studentId), [studentId])

  const statuses = useMemo(() => courseStatuses(courses.data?.items, enrollments.data), [courses.data, enrollments.data])
  const tracks = useMemo(() => {
    const byTopic = {}
    for (const c of courses.data?.items || []) (byTopic[c.topic] ||= []).push(c)
    return Object.entries(byTopic).map(([topic, list]) => ({
      topic,
      courses: list.sort((a, b) => a.level - b.level || a.code.localeCompare(b.code)),
    }))
  }, [courses.data])

  if ((courses.loading && !courses.data) || (enrollments.loading && !enrollments.data)) return <PageSkeleton cards={3} />
  const error = courses.error || enrollments.error
  if (error) return <ErrorState error={error} onRetry={() => { courses.reload(); enrollments.reload() }} />

  const all = courses.data.items
  const count = (s) => all.filter((c) => statuses.get(c.id)?.status === s).length
  const upNext = all.filter((c) => statuses.get(c.id)?.status === 'available')
    .sort((a, b) => a.level - b.level || a.code.localeCompare(b.code)).slice(0, 5)

  return (
    <div className="space-y-6">
      <PageHeader title="Learning Roadmap" description="Every course track, ordered by level, with your real progress and prerequisite locks." />
      <Notice title="How this roadmap is built">
        It is computed from course prerequisites and your enrolments — not by an AI model.
        Personalised, model-ranked paths are added in Phase 5 (AI/ML integration).
      </Notice>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {['completed', 'active', 'available', 'locked'].map((s) => {
          const meta = STATUS_META[s]
          return (
            <Card key={s} bodyClassName="flex items-center justify-between">
              <Badge tone={meta.tone} icon={meta.icon}>{meta.label}</Badge>
              <span className="text-2xl font-semibold text-ink tabular-nums">{count(s)}</span>
            </Card>
          )
        })}
      </div>
      <Card title="Roadmap completion" subtitle={`${count('completed')} of ${all.length} courses completed`}>
        <ProgressBar value={all.length ? count('completed') / all.length : 0} showValue />
      </Card>

      <div className="grid gap-6 xl:grid-cols-4">
        <div className="space-y-4 xl:col-span-3">
          {tracks.map(({ topic, courses: list }) => {
            const done = list.filter((c) => statuses.get(c.id)?.status === 'completed').length
            return (
              <Card key={topic} title={topic} subtitle={`${done}/${list.length} completed`}>
                <ol className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                  {list.map((c, i) => (
                    <li key={c.id} className="relative">
                      <span className="mb-1 flex items-center gap-1 text-xs font-medium text-ink-3">
                        Step {i + 1}{i < list.length - 1 && <ChevronRight className="size-3.5" aria-hidden />}
                      </span>
                      <Node course={c} status={statuses.get(c.id)} onOpen={setOpenId} />
                    </li>
                  ))}
                </ol>
              </Card>
            )
          })}
        </div>
        <Card title="Unlocked next" subtitle="Prerequisites met · lowest level first" className="h-fit">
          {upNext.length === 0 ? (
            <EmptyState icon={MapIcon} title="Nothing unlocked" message="Finish your active courses to unlock new ones." />
          ) : (
            <ul className="space-y-2">
              {upNext.map((c) => (
                <li key={c.id}>
                  <button onClick={() => setOpenId(c.id)} className="w-full rounded-lg border border-line p-3 text-left hover:bg-surface-2">
                    <p className="text-sm font-medium text-ink">{c.title}</p>
                    <p className="text-xs text-ink-3">{c.code} · {c.difficulty} · {c.content_format}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <CourseDetailModal courseId={openId} status={openId ? statuses.get(openId) : null}
                         onClose={() => setOpenId(null)} onChanged={() => { enrollments.reload(); refresh() }} />
    </div>
  )
}
