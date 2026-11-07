import { useState } from 'react'
import { BookOpen, Library, XCircle } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import { useToast } from '../context/ToastContext'
import Badge from '../components/ui/Badge'
import { formatDate } from '../utils/format'
import PageHeader from '../components/ui/PageHeader'
import Tabs from '../components/ui/Tabs'
import Button from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import EnrollmentCard from '../components/learning/EnrollmentCard'

const EMPTY = {
  active: ['No active courses', 'Enroll in a course from the catalog to start learning.'],
  completed: ['No completed courses yet', 'Finish all lessons of a course to complete it.'],
  dropped: ['No paused courses', 'Courses you pause appear here so you can resume them.'],
  requests: ['No access requests', 'Request access to a locked course from the catalog; an administrator reviews it.'],
}

export default function MyLearning() {
  const { studentId } = useStudent()
  const [tab, setTab] = useState('active')
  const toast = useToast()
  const { data, error, loading, reload, setData } = useApi(() => api.enrollments.list(studentId), [studentId])
  const requests = useApi(() => api.enrollmentRequests.list(studentId), [studentId])
  const shown = requests.data?.filter((r) => r.status !== 'cancelled') || []
  const waiting = shown.filter((r) => r.status === 'pending').length
  const withdraw = async (r) => {
    try {
      await api.enrollmentRequests.cancel(studentId, r.id)
      toast.success('Request withdrawn', r.course.title)
      requests.reload()
    } catch (e) {
      toast.error('Could not withdraw the request', e.message)
    }
  }

  const count = (status) => data?.filter((e) => e.status === status).length ?? null
  const list = tab === 'requests' ? [] : data?.filter((e) => e.status === tab) || []
  const onUpdated = (u) => setData((all) => all.map((e) => (e.id === u.id ? u : e)))

  return (
    <div>
      <PageHeader title="My Learning" description="Track lessons, take quizzes and manage your courses."
                  actions={<Button to="/courses" variant="secondary" icon={Library}>Find a course</Button>} />
      <Tabs label="Course status" value={tab} onChange={setTab}
            tabs={[{ value: 'active', label: 'In progress', count: count('active') },
              { value: 'completed', label: 'Completed', count: count('completed') },
              { value: 'dropped', label: 'Paused', count: count('dropped') },
              { value: 'requests', label: 'Access requests', count: waiting || null }]} />
      <div className="mt-6 space-y-4">
        {loading && !data && [0, 1, 2].map((i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}
        {error && <ErrorState error={error} onRetry={reload} />}
        {tab === 'requests' && shown.length > 0 && (
          <Card bodyClassName="divide-y divide-line p-0">
            {shown.map((r) => (
              <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-sm">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{r.course.code} · {r.course.title}</p>
                  <p className="text-xs text-ink-3">Requested {formatDate(r.requested_at)}{r.note ? ` · ${r.note}` : ''}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={{ pending: 'warning', approved: 'good', rejected: 'critical' }[r.status]}>{{ pending: 'Pending', approved: 'Approved', rejected: 'Rejected' }[r.status]}</Badge>
                  {r.status === 'pending' && <Button size="sm" variant="ghost" icon={XCircle} onClick={() => withdraw(r)}>Withdraw</Button>}
                </div>
              </div>
            ))}
          </Card>
        )}
        {(tab === 'requests' ? requests.data && shown.length === 0 : data && list.length === 0) && (
          <Card>
            <EmptyState icon={BookOpen} title={EMPTY[tab][0]} message={EMPTY[tab][1]}
                        action={tab !== 'dropped' && <Button to="/courses" icon={Library}>Browse the catalog</Button>} />
          </Card>
        )}
        {list.map((e, i) => (
          <EnrollmentCard key={e.id} enrollment={e} onUpdated={onUpdated} defaultOpen={tab === 'active' && i === 0} />
        ))}
      </div>
    </div>
  )
}
