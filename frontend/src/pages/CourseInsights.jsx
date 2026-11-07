import { ArrowLeft, Compass, ListChecks } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import PageHeader from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import Button from '../components/ui/Button'
import ProgressBar from '../components/ui/ProgressBar'
import { EmptyState, ErrorState, Notice, PageSkeleton } from '../components/ui/States'
import RecommendationList from '../components/ai/RecommendationList'
import { ModelBadge } from '../components/ai/AiParts'
import { DifficultyCard, PredictionsCard, SkillMasteryCard } from '../components/ai/ModelCards'

/** Personalised guidance for ONE enrolled course: progress, weak skills, difficulty, predicted quiz score, next steps. */
export default function CourseInsights() {
  const { courseId } = useParams()
  const navigate = useNavigate()
  const { studentId, version } = useStudent()
  const cid = Number(courseId)
  const guidance = useApi(() => api.ai.guidance(studentId, cid), [studentId, cid, version])
  const enrollments = useApi(() => api.enrollments.list(studentId), [studentId, version])

  if (guidance.loading && !guidance.data) return <PageSkeleton />
  if (guidance.error) {
    return guidance.error.status === 404
      ? <EmptyState title="You are not enrolled in this course"
                    message="Course insights are only available for courses you are enrolled in."
                    action={<Button to="/courses" icon={ListChecks}>Browse the catalog</Button>} />
      : <ErrorState error={guidance.error} onRetry={guidance.reload} />
  }
  const g = guidance.data
  const enrollment = enrollments.data?.find((e) => e.course.id === cid)
  const asState = (data) => ({ data, loading: false, error: null })

  return (
    <div className="space-y-6">
      <Link to="/learning" className="inline-flex items-center gap-1 text-sm text-ink-3 hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> My Learning
      </Link>
      <PageHeader title={g.scope.course_title} description={`${g.scope.course_code} · personalised guidance for this course`}
                  actions={enrollment?.next_lesson && <Button to="/learning" icon={ListChecks}>Next: {enrollment.next_lesson.title}</Button>} />

      {enrollment && (
        <Card title="Your progress in this course">
          <ProgressBar value={enrollment.progress} />
          <p className="mt-2 text-sm text-ink-3">{enrollment.completed_lessons} of {enrollment.total_lessons} lessons · status: {enrollment.status}</p>
        </Card>
      )}

      <Card title="What to do next" action={<ModelBadge data={g} />}>
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">
          {g.actions.map((a) => <li key={a}>{a}</li>)}
        </ul>
        <Notice icon={Compass} title="How this is computed">{g.note}</Notice>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <SkillMasteryCard state={asState(g.skills)} />
        <DifficultyCard state={asState(g.difficulty)} />
        <PredictionsCard state={asState(g.predictions)} />
        <Card title="Related courses to take next" subtitle="Same topic, or unlocked by this course">
          {g.next_courses.items.length === 0
            ? <p className="text-sm text-ink-3">No further suggestions for this course right now.</p>
            : <RecommendationList items={g.next_courses.items} onOpen={() => navigate('/courses')} />}
        </Card>
      </div>
    </div>
  )
}
