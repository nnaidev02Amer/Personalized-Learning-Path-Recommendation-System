import { useState } from 'react'
import { BookOpen, Library } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
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
}

export default function MyLearning() {
  const { studentId } = useStudent()
  const [tab, setTab] = useState('active')
  const { data, error, loading, reload, setData } = useApi(() => api.enrollments.list(studentId), [studentId])

  const count = (status) => data?.filter((e) => e.status === status).length ?? null
  const list = data?.filter((e) => e.status === tab) || []
  const onUpdated = (u) => setData((all) => all.map((e) => (e.id === u.id ? u : e)))

  return (
    <div>
      <PageHeader title="My Learning" description="Track lessons, take quizzes and manage your courses."
                  actions={<Button to="/courses" variant="secondary" icon={Library}>Find a course</Button>} />
      <Tabs label="Course status" value={tab} onChange={setTab}
            tabs={[{ value: 'active', label: 'In progress', count: count('active') },
              { value: 'completed', label: 'Completed', count: count('completed') },
              { value: 'dropped', label: 'Paused', count: count('dropped') }]} />
      <div className="mt-6 space-y-4">
        {loading && !data && [0, 1, 2].map((i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}
        {error && <ErrorState error={error} onRetry={reload} />}
        {data && list.length === 0 && (
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
