import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useStudent } from '../context/StudentContext'
import PageHeader from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import Tabs from '../components/ui/Tabs'
import { Select } from '../components/ui/Form'
import Badge from '../components/ui/Badge'
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
  const { isAdmin } = useAuth()
  const [courseId, setCourseId] = useState('')
  const [method, setMethod] = useState('hybrid')
  const [openId, setOpenId] = useState(null)

  const cid = courseId ? Number(courseId) : undefined
  const status = useApi(isAdmin ? () => api.ai.status() : null, [isAdmin])   // training details are admin-only
  const recs = useApi(() => api.ai.recommendations(studentId, method, 5, cid), [studentId, method, cid, version])
  const skills = useApi(() => api.ai.skills(studentId, cid), [studentId, cid, version])
  const difficulty = useApi(() => api.ai.difficulty(studentId, cid), [studentId, cid, version])
  const predictions = useApi(() => api.ai.predictions(studentId, cid), [studentId, cid, version])
  const style = useApi(() => api.ai.learningStyle(studentId), [studentId, version])
  const history = useApi(() => api.ai.recommendationHistory(studentId, 8), [studentId, version, recs.data])
  const courses = useApi(() => api.courses.list(), [])
  const enrollments = useApi(() => api.enrollments.list(studentId), [studentId, version])
  const statuses = useMemo(() => courseStatuses(courses.data?.items, enrollments.data), [courses.data, enrollments.data])

  const data = status.data?.training_data
  const ev = recs.data?.evaluation

  return (
    <div className="space-y-6">
      <PageHeader title="AI Recommendations" description="Personalised suggestions from the project's trained models."
                  actions={isAdmin && <Button to="/models" variant="secondary" icon={FlaskConical}>Model evaluation</Button>} />

      <Notice title="Real model outputs — trained on this database">
        {status.data && !status.data.trained && 'Models are training in the background (about 10 seconds); results appear when ready. '}
        {data ? `Training data: ${data.students} students (${data.synthetic_students} with synthetic seeded histories, ${data.real_students} created in this app), ${data.quiz_attempts} quiz attempts. ` : ''}
        Every card states how its model compared with a simple baseline on held-out data.{' '}
        {isAdmin && <Link to="/models" className="font-medium text-brand hover:underline">See full evaluation</Link>}
      </Notice>

      <div className="max-w-sm">
        <Select label="Scope" value={courseId} onChange={(e) => setCourseId(e.target.value)} placeholder="All my courses"
                options={(enrollments.data || []).filter((en) => en.status !== 'dropped')
                  .map((en) => ({ value: en.course.id, label: en.course.title }))}
                hint="Limit skills, difficulty, predictions and suggestions to one enrolled course. The models themselves are shared by all learners." />
      </div>

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

      <Card title="Recommendation history" subtitle="What was suggested to you before (a new entry is saved when the list changes)">
        {history.data?.items.length ? (
          <ul className="divide-y divide-line text-sm">
            {history.data.items.map((h) => (
              <li key={h.id} className="py-2">
                <p className="flex flex-wrap items-center gap-2 text-ink">
                  <span className="text-xs text-ink-3">{new Date(h.created_at).toLocaleString()}</span>
                  <Badge>{h.method}</Badge>
                  {h.course_id && <Badge tone="brand">course-scoped</Badge>}
                </p>
                <p className="mt-0.5 text-ink-2">{h.items.map((i) => i.title).join(' · ')}</p>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-ink-3">Nothing saved yet.</p>}
      </Card>

      <CourseDetailModal courseId={openId} status={openId ? statuses.get(openId) : null}
                         onClose={() => setOpenId(null)} onChanged={() => { enrollments.reload(); refresh() }} />
    </div>
  )
}
