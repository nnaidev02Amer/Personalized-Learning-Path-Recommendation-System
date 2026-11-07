import { CheckCircle2, CircleDot, Hourglass, Lock, PauseCircle, Unlock } from 'lucide-react'
import { FileText, Headphones, ListChecks, PlayCircle } from 'lucide-react'

export const STATUS_META = {
  completed: { label: 'Completed', tone: 'good', icon: CheckCircle2 },
  active: { label: 'In progress', tone: 'brand', icon: CircleDot },
  dropped: { label: 'Paused', tone: 'neutral', icon: PauseCircle },
  pending: { label: 'Request pending', tone: 'warning', icon: Hourglass },
  available: { label: 'Available', tone: 'neutral', icon: Unlock },
  locked: { label: 'Locked', tone: 'warning', icon: Lock },
}

export const FORMAT_ICON = { Videos: PlayCircle, Articles: FileText, Podcasts: Headphones, Quizzes: ListChecks }

/**
 * Status of every course for one student, from real enrolments + prerequisites.
 * Returns Map(courseId -> { status, enrollment, missing: [codes] }).
 */
export function courseStatuses(courses, enrollments, requests) {
  const pendingByCourse = new Map((requests || []).filter((r) => r.status === 'pending').map((r) => [r.course.id, r]))
  const lastDecision = new Map()
  for (const r of requests || []) if (r.status === 'rejected' && !lastDecision.has(r.course.id)) lastDecision.set(r.course.id, r)
  const byCourse = new Map((enrollments || []).map((e) => [e.course.id, e]))
  const completedCodes = new Set((enrollments || []).filter((e) => e.status === 'completed').map((e) => e.course.code))
  const result = new Map()
  for (const course of courses || []) {
    const enrollment = byCourse.get(course.id)
    const missing = course.prerequisite_codes.filter((code) => !completedCodes.has(code))
    let status
    const request = pendingByCourse.get(course.id)
    if (enrollment && enrollment.status !== 'dropped') status = enrollment.status
    else if (request) status = 'pending'
    else if (enrollment) status = enrollment.status
    else status = missing.length ? 'locked' : 'available'
    result.set(course.id, { status, enrollment, missing, request, rejected: lastDecision.get(course.id) })
  }
  return result
}
