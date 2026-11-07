import { useMemo, useState } from 'react'
import { Search, SearchX, X } from 'lucide-react'
import { api } from '../api/client'
import { useApi, useDebounced } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import PageHeader from '../components/ui/PageHeader'
import { Select } from '../components/ui/Form'
import Button from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import CourseCard from '../components/course/CourseCard'
import CourseDetailModal from '../components/course/CourseDetailModal'
import { courseStatuses } from '../utils/courseStatus'

const STATUS_FILTERS = [
  { value: 'available', label: 'Available to start' },
  { value: 'pending', label: 'Awaiting approval' },
  { value: 'active', label: 'In progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'locked', label: 'Locked' },
]

export default function CourseCatalog() {
  const { studentId } = useStudent()
  const [filters, setFilters] = useState({ search: '', topic: '', difficulty: '', content_format: '', status: '' })
  const [openId, setOpenId] = useState(null)
  const search = useDebounced(filters.search)

  const meta = useApi(() => api.meta(), [])
  const courses = useApi(() => api.courses.list({ search, topic: filters.topic, difficulty: filters.difficulty,
    content_format: filters.content_format }), [search, filters.topic, filters.difficulty, filters.content_format])
  const enrollments = useApi(() => api.enrollments.list(studentId), [studentId])
  const requests = useApi(() => api.enrollmentRequests.list(studentId), [studentId])

  const statuses = useMemo(() => courseStatuses(courses.data?.items, enrollments.data, requests.data),
    [courses.data, enrollments.data, requests.data])
  const items = (courses.data?.items || []).filter((c) => !filters.status || statuses.get(c.id)?.status === filters.status)

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }))
  const active = Object.values(filters).some(Boolean)

  return (
    <div>
      <PageHeader title="Course Catalog"
                  description={courses.data ? `${courses.data.total} course${courses.data.total === 1 ? '' : 's'} match your filters` : 'Browse all courses'} />

      <Card bodyClassName="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="relative sm:col-span-2 lg:col-span-1">
          <span className="sr-only">Search courses</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <input value={filters.search} onChange={set('search')} placeholder="Search courses…"
                 className="h-10 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-sm text-ink placeholder:text-ink-3 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25" />
        </label>
        <Select aria-label="Topic" value={filters.topic} onChange={set('topic')} placeholder="All topics" options={meta.data?.topics || []} />
        <Select aria-label="Difficulty" value={filters.difficulty} onChange={set('difficulty')} placeholder="All levels" options={meta.data?.difficulties || []} />
        <Select aria-label="Format" value={filters.content_format} onChange={set('content_format')} placeholder="All formats" options={meta.data?.content_types || []} />
        <Select aria-label="Your status" value={filters.status} onChange={set('status')} placeholder="Any status" options={STATUS_FILTERS} />
      </Card>
      {active && (
        <div className="mt-3">
          <Button size="sm" variant="ghost" icon={X} onClick={() => setFilters({ search: '', topic: '', difficulty: '', content_format: '', status: '' })}>
            Clear filters
          </Button>
        </div>
      )}

      <div className="mt-6">
        {courses.error && <ErrorState error={courses.error} onRetry={courses.reload} />}
        {courses.loading && !courses.data && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-56 rounded-2xl" />)}</div>
        )}
        {courses.data && items.length === 0 && (
          <Card><EmptyState icon={SearchX} title="No courses found" message="Try a different search term or clear the filters." /></Card>
        )}
        {items.length > 0 && (
          <div className={`grid gap-4 sm:grid-cols-2 xl:grid-cols-3 ${courses.loading ? 'opacity-60' : ''}`}>
            {items.map((c) => <CourseCard key={c.id} course={c} status={statuses.get(c.id)} onOpen={(course) => setOpenId(course.id)} />)}
          </div>
        )}
      </div>

      <CourseDetailModal courseId={openId} status={openId ? statuses.get(openId) : null}
                         onClose={() => setOpenId(null)} onChanged={() => { enrollments.reload(); requests.reload(); courses.reload() }} />
    </div>
  )
}
