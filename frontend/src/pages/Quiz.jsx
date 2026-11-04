import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, RotateCcw, Send, XCircle } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import { useToast } from '../context/ToastContext'
import PageHeader from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { ErrorState, Notice, PageSkeleton } from '../components/ui/States'

export default function Quiz() {
  const { quizId } = useParams()
  const navigate = useNavigate()
  const { studentId, refresh } = useStudent()
  const toast = useToast()
  const quiz = useApi(() => api.quizzes.get(quizId), [quizId])
  const [answers, setAnswers] = useState({})
  const [result, setResult] = useState(null)
  const [submitError, setSubmitError] = useState(null)
  const [busy, setBusy] = useState(false)
  const started = useRef(Date.now())

  useEffect(() => { started.current = Date.now() }, [quizId])

  if (quiz.loading && !quiz.data) return <PageSkeleton cards={0} />
  if (quiz.error) return <ErrorState error={quiz.error} onRetry={quiz.reload} />

  const q = quiz.data
  const answered = Object.keys(answers).length
  const feedback = new Map(result?.feedback.map((f) => [f.question_id, f]))

  const submit = async () => {
    setBusy(true)
    setSubmitError(null)
    try {
      const minutes = Math.max(0.5, Math.round((Date.now() - started.current) / 6000) / 10)
      const r = await api.quizzes.submit(studentId, q.id, {
        answers: q.questions.map((question) => answers[question.id]),
        time_taken_min: minutes,
      })
      setResult(r)
      refresh()
      window.scrollTo({ top: 0, behavior: 'smooth' })
      toast[r.passed ? 'success' : 'info'](r.passed ? 'Quiz passed' : 'Quiz submitted', `You scored ${r.score}%.`)
    } catch (e) {
      setSubmitError(e)
    } finally {
      setBusy(false)
    }
  }

  const retry = () => {
    setAnswers({})
    setResult(null)
    started.current = Date.now()
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate(-1)}>Back</Button>
      <PageHeader title={q.title} description={`${q.course.code} · ${q.course.title} · ${q.questions.length} questions · pass mark ${q.pass_score}%`} />

      {result && (
        <Card>
          <div className="flex flex-wrap items-center gap-4">
            <span className={`grid size-16 place-items-center rounded-2xl text-xl font-semibold ${result.passed ? 'bg-good-soft text-good' : 'bg-critical-soft text-critical'}`}>
              {Math.round(result.score)}%
            </span>
            <div className="flex-1">
              <p className="text-lg font-semibold text-ink">{result.passed ? 'Well done — you passed!' : 'Not quite — review and try again'}</p>
              <p className="text-sm text-ink-3">{result.correct} of {result.total} correct · saved to your progress</p>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" icon={RotateCcw} onClick={retry}>Retake</Button>
              <Button to="/analytics">View analytics</Button>
            </div>
          </div>
        </Card>
      )}

      {submitError && (
        submitError.code === 'not_enrolled'
          ? <Notice tone="warning" title="Enroll first">{submitError.message}. <Button to="/courses" size="sm" variant="ghost">Open catalog</Button></Notice>
          : <ErrorState compact error={submitError} />
      )}

      <ol className="space-y-4">
        {q.questions.map((question) => {
          const f = feedback.get(question.id)
          return (
            <li key={question.id}>
              <Card>
                <fieldset disabled={Boolean(result)}>
                  <legend className="flex w-full items-start justify-between gap-3">
                    <span className="font-medium text-ink">{question.position}. {question.prompt}</span>
                    <Badge>{question.skill.replace(/-/g, ' ')}</Badge>
                  </legend>
                  <div className="mt-4 grid gap-2">
                    {question.options.map((option, i) => {
                      const selected = answers[question.id] === i
                      let state = selected ? 'border-brand bg-brand-soft' : 'border-line hover:bg-surface-2'
                      if (f && i === f.correct_option) state = 'border-good bg-good-soft'
                      else if (f && selected && !f.is_correct) state = 'border-critical bg-critical-soft'
                      return (
                        <label key={i} className={`flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-sm transition-colors ${state}`}>
                          <input type="radio" name={`q-${question.id}`} checked={selected} className="accent-[var(--brand)]"
                                 onChange={() => setAnswers((a) => ({ ...a, [question.id]: i }))} />
                          <span className="flex-1 text-ink">{option}</span>
                          {f && i === f.correct_option && <CheckCircle2 className="size-5 text-good" aria-label="Correct answer" />}
                          {f && selected && !f.is_correct && <XCircle className="size-5 text-critical" aria-label="Your answer" />}
                        </label>
                      )
                    })}
                  </div>
                  {f && <p className="mt-3 text-sm text-ink-2"><span className="font-medium">Explanation:</span> {f.explanation}</p>}
                </fieldset>
              </Card>
            </li>
          )
        })}
      </ol>

      {!result && (
        <div className="sticky bottom-4 flex items-center justify-between gap-3 rounded-2xl border border-line bg-surface p-4 shadow-lg">
          <span className="text-sm text-ink-3">{answered} of {q.questions.length} answered</span>
          <Button icon={Send} loading={busy} disabled={answered < q.questions.length} onClick={submit}>Submit answers</Button>
        </div>
      )}
    </div>
  )
}
