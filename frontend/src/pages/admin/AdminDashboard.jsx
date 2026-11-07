import { AlertTriangle, BookOpen, CheckCircle2, ClipboardCheck, GraduationCap, Hourglass, Inbox, KeyRound, Library, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import PageHeader from '../../components/ui/PageHeader'
import { Card, StatCard } from '../../components/ui/Card'
import Badge from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import { EmptyState, ErrorState, PageSkeleton } from '../../components/ui/States'

export default function AdminDashboard() {
  const overview = useApi(() => api.admin.overview(), [])
  const atRisk = useApi(() => api.admin.students({ at_risk: true, limit: 6 }), [])
  const perCourse = useApi(() => api.admin.courseEnrollments(), [])
  const recent = useApi(() => api.admin.students({ limit: 8 }), [])

  if (overview.loading && !overview.data) return <PageSkeleton />
  if (overview.error) return <ErrorState error={overview.error} onRetry={overview.reload} />
  const o = overview.data


  return (
    <div className="space-y-6">
      <PageHeader title="Administration" description="Monitor learners, courses and the learning system."
                  actions={<>
                    <Button to="/admin/requests" icon={Inbox} variant="secondary">Requests{o.requests.pending ? ` (${o.requests.pending})` : ''}</Button>
                    <Button to="/admin/accounts" icon={KeyRound} variant="secondary">Accounts</Button>
                    <Button to="/admin/courses" icon={Library}>Manage courses</Button>
                  </>} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Users} label="Registered students" value={o.students.registered}
                  hint={`${o.students.registered_last_7_days} new this week · ${o.students.seeded} sample learners for the AI models`} />
        <StatCard icon={BookOpen} label="Courses" value={o.courses.active}
                  hint={o.courses.archived ? `${o.courses.archived} archived` : 'all active'} tone="good" />
        <StatCard icon={GraduationCap} label="Enrolments" value={o.enrollments.total}
                  hint={`${o.enrollments.active} active · ${o.enrollments.completed} completed · ${o.enrollments.dropped} dropped`} />
        <StatCard icon={ClipboardCheck} label="Quiz attempts" value={o.quiz_attempts.total}
                  hint={o.quiz_attempts.average_score == null ? 'no attempts yet' : `average score ${o.quiz_attempts.average_score}%`}
                  tone="warning" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard icon={Hourglass} label="Pending requests" value={o.requests.pending} tone="warning"
                  hint={o.requests.pending ? 'waiting for your decision' : 'nothing waiting'} />
        <StatCard icon={CheckCircle2} label="Approved requests" value={o.requests.approved} tone="good" hint="students now studying" />
        <StatCard icon={Inbox} label="Rejected requests" value={o.requests.rejected} tone="critical" hint="declined by an administrator" />
      </div>

      <Card title="Students enrolled per course" subtitle="Approved enrolments and requests waiting for a decision"
            action={<Link to="/admin/requests" className="text-sm font-medium text-brand hover:underline">Review requests</Link>}>
        {perCourse.loading && !perCourse.data ? <p className="text-sm text-ink-3">Loading…</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-ink-3"><tr>
                <th className="py-2 pr-4 font-medium">Course</th><th className="px-4 py-2 text-right font-medium">Enrolled</th>
                <th className="px-4 py-2 text-right font-medium">In progress</th><th className="px-4 py-2 text-right font-medium">Completed</th>
                <th className="py-2 pl-4 text-right font-medium">Pending</th></tr></thead>
              <tbody className="divide-y divide-line">
                {(perCourse.data || []).map((c) => (
                  <tr key={c.course_id} className={c.is_active ? '' : 'opacity-60'}>
                    <td className="py-2 pr-4 text-ink">{c.title}<span className="ml-2 text-xs text-ink-3">{c.code}{c.is_active ? '' : ' · hidden'}</span></td>
                    <td className="px-4 py-2 text-right tabular-nums">{c.enrolled}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{c.active}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{c.completed}</td>
                    <td className="py-2 pl-4 text-right tabular-nums">{c.pending_requests ? <Badge tone="warning">{c.pending_requests}</Badge> : 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Student progress and performance" subtitle="Enrolments and quiz results per learner"
            action={<Link to="/admin/students" className="text-sm font-medium text-brand hover:underline">All students</Link>}>
        {recent.loading && !recent.data ? <p className="text-sm text-ink-3">Loading…</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-ink-3"><tr>
                <th className="py-2 pr-4 font-medium">Student</th><th className="px-4 py-2 text-right font-medium">Courses</th>
                <th className="px-4 py-2 text-right font-medium">Completed</th><th className="px-4 py-2 text-right font-medium">Quiz attempts</th>
                <th className="py-2 pl-4 text-right font-medium">Average score</th></tr></thead>
              <tbody className="divide-y divide-line">
                {(recent.data?.items || []).map((s) => (
                  <tr key={s.id}>
                    <td className="py-2 pr-4 text-ink">{s.name}{s.at_risk && <Badge tone="warning" className="ml-2">needs help</Badge>}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{s.enrollments}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{s.completed_enrollments}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{s.quiz_attempts}</td>
                    <td className="py-2 pl-4 text-right tabular-nums">{s.average_score == null ? '—' : `${s.average_score}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Most popular courses" action={<Link to="/admin/courses" className="text-sm font-medium text-brand hover:underline">All courses</Link>}>
          {o.top_courses.length === 0 ? <EmptyState title="No enrolments yet" /> : (
            <ol className="space-y-2">
              {o.top_courses.map((c, i) => (
                <li key={c.course_id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate text-ink"><span className="mr-2 text-ink-3">{i + 1}.</span>{c.title}
                    <span className="ml-2 text-xs text-ink-3">{c.code}</span></span>
                  <Badge tone="brand">{c.enrollments} enrolled</Badge>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <Card title="Learners who may need help"
              subtitle="Average quiz score under 60% over at least 3 attempts"
              action={<Badge tone={o.at_risk_students ? 'warning' : 'good'} icon={AlertTriangle}>{o.at_risk_students} flagged</Badge>}>
          {atRisk.loading ? <p className="text-sm text-ink-3">Loading…</p> : atRisk.data?.items.length === 0 ? (
            <EmptyState title="Nobody is flagged" message="No learner currently meets the at-risk rule." />
          ) : (
            <ul className="divide-y divide-line">
              {atRisk.data?.items.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="min-w-0"><span className="block truncate text-ink">{s.name}</span>
                    <span className="text-xs text-ink-3">{s.quiz_attempts} attempts · average {s.average_score}%</span></span>
                  <Badge tone="warning">{s.average_score}%</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Learning system">
        <p className="text-sm text-ink-2">
          Recommendations, knowledge tracing, difficulty and score prediction use models trained jointly on all learners.
          {' '}<Link to="/models" className="font-medium text-brand hover:underline">Open the model evaluation</Link> to see
          how each model compares with its baseline, or retrain after adding courses.
        </p>
      </Card>
    </div>
  )
}
