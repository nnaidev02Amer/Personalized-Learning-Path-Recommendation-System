import { Clock, KeyRound, Layers, Users } from 'lucide-react'
import Badge, { DIFFICULTY_TONE } from '../ui/Badge'
import StarRating from '../ui/StarRating'
import ProgressBar from '../ui/ProgressBar'
import { FORMAT_ICON, STATUS_META } from '../../utils/courseStatus'

export default function CourseCard({ course, status, onOpen }) {
  const meta = STATUS_META[status?.status || 'available']
  const FormatIcon = FORMAT_ICON[course.content_format]
  return (
    <button onClick={() => onOpen(course)}
            className="group flex h-full flex-col rounded-2xl border border-line bg-surface p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-md focus-visible:outline-2 focus-visible:outline-brand">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-semibold tracking-wide text-ink-3">{course.code} · {course.topic}</span>
        <Badge tone={meta.tone} icon={meta.icon}>{meta.label}</Badge>
      </div>
      <h3 className="mt-2 text-base font-semibold text-ink group-hover:text-brand">{course.title}</h3>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Badge tone={DIFFICULTY_TONE[course.difficulty]}>{course.difficulty}</Badge>
        <Badge icon={FormatIcon}>{course.content_format}</Badge>
        {course.is_locked && !status?.enrollment && <Badge tone="warning" icon={KeyRound}>Approval needed</Badge>}
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-ink-3">
        <span className="flex items-center gap-1"><Clock className="size-3.5" aria-hidden />{course.duration_hours}h</span>
        <span className="flex items-center gap-1"><Layers className="size-3.5" aria-hidden />{course.lesson_count} lessons</span>
        <span className="flex items-center gap-1"><Users className="size-3.5" aria-hidden />{course.enrolled_count}</span>
      </div>
      <div className="mt-auto pt-4">
        {status?.status === 'active' && status.enrollment ? (
          <ProgressBar value={status.enrollment.progress} size="sm" label="Your progress" />
        ) : status?.status === 'locked' ? (
          <p className="text-xs text-warning">Requires {status.missing.join(', ')}</p>
        ) : (
          <div className="flex items-center gap-2 text-xs text-ink-3">
            <StarRating value={course.average_rating || 0} size="sm" />
            {course.average_rating ? course.average_rating.toFixed(1) : 'No ratings yet'}
          </div>
        )}
      </div>
    </button>
  )
}
