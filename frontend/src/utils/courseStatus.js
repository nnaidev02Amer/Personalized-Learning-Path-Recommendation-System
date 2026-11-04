import { CheckCircle2, CircleDot, Lock, PauseCircle, Unlock } from 'lucide-react'
import { FileText, Headphones, ListChecks, PlayCircle } from 'lucide-react'

export const STATUS_META = {
  completed: { label: 'Completed', tone: 'good', icon: CheckCircle2 },
  active: { label: 'In progress', tone: 'brand', icon: CircleDot },
  dropped: { label: 'Paused', tone: 'neutral', icon: PauseCircle },
  available: { label: 'Available', tone: 'neutral', icon: Unlock },
  locked: { label: 'Locked', tone: 'warning', icon: Lock },
}

export const FORMAT_ICON = { Videos: PlayCircle, Articles: FileText, Podcasts: Headphones, Quizzes: ListChecks }

/**
 * Status of every course for one student, from real enrolments + prerequisites.
 * Returns Map(courseId -> { status, enrollment, missing: [codes] }).
 */
export function courseStatuses(courses, enrollments) {
  const byCourse = new Map((enrollments || []).map((e) => [e.course.id, e]))
  const completedCodes = new Set((enrollments || []).filter((e) => e.status === 'completed').map((e) => e.course.code))
  const result = new Map()
  for (const course of courses || []) {
    const enrollment = byCourse.get(course.id)
    const missing = course.prerequisite_codes.filter((code) => !completedCodes.has(code))
    let status
    if (enrollment) status = enrollment.status
    else status = missing.length ? 'locked' : 'available'
    result.set(course.id, { status, enrollment, missing })
  }
  return result
}
