import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import PageHeader from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import Tabs from '../components/ui/Tabs'
import Button from '../components/ui/Button'
import { ErrorState, Notice, Skeleton } from '../components/ui/States'
import CourseDetailModal from '../components/course/CourseDetailModal'
import RecommendationList from '../components/ai/RecommendationList'
import AssistantChat from '../components/ai/AssistantChat'
import { ModelBadge } from '../components/ai/AiParts'
import { DifficultyCard, PredictionsCard, SkillMasteryCard, StyleCard } from '../components/ai/ModelCards'
import { courseStatuses } from '../utils/courseStatus'

const METHODS = [
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'collaborative', label: 'Collaborative' },
  { value: 'content', label: 'Content-based' },
  { value: 'popularity', label: 'Popular (baseline)' },
]
const METHOD_TEXT = {
  hybrid: 'Blend of collaborative and content-based scores (weight tuned on held-out students).',
  collaborative: 'Item-to-item similarity from what learners with similar enrolments took.',
  content: 'Similarity of course text, your topic interests and your preferred format.',
  popularity: 'Most-enrolled unlocked courses — the baseline the models are compared with.',
}

export default function Recommendations() {
  const { studentId, version, refresh } = useStudent()
  const [method, setMethod] = useState('hybrid')
  const [openId, setOpenId] = useState(null)

  const status = useApi(() => api.ai.status(), [])
  const recs = useApi(() => api.ai.recommendations(studentId, method, 5), [studentId, method, version])
  const skills = useApi(() => api.ai.skills(studentId), [studentId, version])
  const difficulty = useApi(() => api.ai.difficulty(studentId), [studentId, version])
  const predictions = useApi(() => api.ai.predictions(studentId), [studentId, version])
  const style = useApi(() => api.ai.learningStyle(studentId), [studentId, version])
  const courses = useApi(() => api.courses.list(), [])
  const enrollments = useApi(() => api.enrollments.list(studentId), [studentId, version])
  const statuses = useMemo(() => courseStatuses(courses.data?.items, enrollments.data), [courses.data, enrollments.data])

  const data = status.data?.training_data
  const ev = recs.data?.evaluation

  return (
    <div className="space-y-6">
      <PageHeader title="AI Recommendations" description="Personalised suggestions from the project's trained models."
                  actions={<Button to="/models" variant="secondary" icon={FlaskConical}>Model evaluation</Button>} />

      <Notice title="Real model outputs — trained on this database">
        {status.data && !status.data.trained && 'Models are training in the background (about 10 seconds); results appear when ready. '}
        {data ? `Training data: ${data.students} students (${data.synthetic_students} with synthetic seeded histories, ${data.real_students} created in this app), ${data.quiz_attempts} quiz attempts. ` : ''}
        Every card states how its model compared with a simple baseline on held-out data.{' '}
        <Link to="/models" className="font-medium text-brand hover:underline">See full evaluation</Link>
      </Notice>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Recommended next courses" subtitle={METHOD_TEXT[method]} className="xl:col-span-2"
              action={<ModelBadge data={recs.data} />}>
          <div className="mb-4"><Tabs label="Recommendation method" value={method} onChange={setMethod} tabs={METHODS} /></div>
          {recs.loading && !recs.data && <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>}
          {recs.error && <ErrorState compact error={recs.error} onRetry={recs.reload} />}
          {recs.data && <RecommendationList items={recs.data.items} onOpen={setOpenId} />}
          {ev && (
            <p className="mt-4 border-t border-line pt-3 text-xs text-ink-3">
              Held-out NDCG@5 for this method: {ev.ndcg_at_5} (popularity baseline {ev.popularity_ndcg_at_5}){ev.beats_popularity == null ? '' : ev.beats_popularity ? ' — significantly better' : ' — not a statistically significant difference'}. Only courses whose prerequisites you have completed are recommended.
            </p>
          )}
        </Card>
        <AssistantChat studentId={studentId} provider={status.data?.assistant_provider} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <SkillMasteryCard state={skills} />
        <DifficultyCard state={difficulty} />
        <PredictionsCard state={predictions} />
        <StyleCard state={style} />
      </div>

      <CourseDetailModal courseId={openId} status={openId ? statuses.get(openId) : null}
                         onClose={() => setOpenId(null)} onChanged={() => { enrollments.reload(); refresh() }} />
    </div>
  )
}
