import { Link } from 'react-router-dom'
import { AlertTriangle, Gauge, LineChart, Puzzle, UserSearch } from 'lucide-react'
import { Card } from '../ui/Card'
import Badge from '../ui/Badge'
import { EmptyState, ErrorState, Skeleton } from '../ui/States'
import { EvalNote, Meter, ModelBadge, masteryTone } from './AiParts'

function Body({ state, children }) {
  if (state.loading && !state.data) return <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8" />)}</div>
  if (state.error) return <ErrorState compact error={state.error} onRetry={state.reload} />
  return children(state.data)
}

const pct = (v) => `${Math.round(v * 100)}%`

export function SkillMasteryCard({ state }) {
  return (
    <Card title="Skill mastery" subtitle="Bayesian Knowledge Tracing over your quiz answers"
          action={<ModelBadge data={state.data} />}>
      <Body state={state}>
        {(d) => (
          <>
            {d.skills.length === 0 ? (
              <EmptyState icon={Puzzle} title="No skills assessed yet" message="Take a course quiz to estimate your skill mastery." />
            ) : (
              <div className="space-y-4">
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
                    {d.gaps.length ? 'Skill gaps (below mastery threshold)' : 'Weakest skills'}
                  </p>
                  <div className="space-y-3">
                    {(d.gaps.length ? d.gaps : d.skills.slice(0, 3)).slice(0, 5).map((s) => (
                      <Meter key={s.skill} label={`${s.skill.replace(/-/g, ' ')} · ${s.topic}`} value={s.mastery}
                             tone={masteryTone(s.mastery)}
                             sublabel={`${s.observations} answer${s.observations === 1 ? '' : 's'}, ${pct(s.accuracy)} correct`} />
                    ))}
                  </div>
                </div>
                {d.topics.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Mastery by topic</p>
                    <div className="space-y-2">
                      {d.topics.map((t) => <Meter key={t.topic} label={`${t.topic} (${t.skills} skills)`} value={t.mean_mastery} tone={masteryTone(t.mean_mastery)} />)}
                    </div>
                  </div>
                )}
              </div>
            )}
            {d.not_yet_assessed.length > 0 && (
              <p className="mt-4 text-xs text-ink-3">Not yet assessed in your active courses: {d.not_yet_assessed.map((s) => s.replace(/-/g, ' ')).join(', ')}</p>
            )}
            <EvalNote>
              Mastery = estimated probability you know a skill (threshold {pct(d.threshold)}). Held-out test: BKT log-loss {d.evaluation.bkt.log_loss}
              {' '}vs {d.evaluation.baseline_global_accuracy.log_loss} for the global-accuracy baseline — {d.beats_baseline ? 'a statistically significant improvement' : 'no significant improvement on this data'}.
              {' '}<Link to="/models" className="text-brand hover:underline">Details</Link>
            </EvalNote>
          </>
        )}
      </Body>
    </Card>
  )
}

export function DifficultyCard({ state }) {
  return (
    <Card title="Adaptive difficulty" subtitle="LinUCB contextual bandit" action={<ModelBadge data={state.data} />}>
      <Body state={state}>
        {(d) => (
          <>
            <div className="flex items-center gap-3 rounded-xl bg-brand-soft p-4">
              <Gauge className="size-6 text-brand" aria-hidden />
              <div>
                <p className="text-xs text-ink-3">Suggested next difficulty</p>
                <p className="text-lg font-semibold text-ink">{d.recommended_difficulty}</p>
              </div>
              {d.exploring && <Badge className="ml-auto" tone="warning">Exploring</Badge>}
            </div>
            <p className="mb-2 mt-4 text-xs text-ink-3">Estimated chance of a productive result (score 60–89%) per level</p>
            <div className="space-y-3">
              {d.arms.map((a) => (
                <Meter key={a.level} label={a.difficulty} value={a.expected_success}
                       tone={a.level === d.recommended_level ? 'brand' : 'warning'}
                       sublabel={`±${Math.round(a.uncertainty * 100)} pts uncertainty · learned from ${a.observations} attempts`} />
              ))}
            </div>
            <EvalNote>
              The bandit updates after every quiz you submit. Held-out Brier score {d.evaluation.linucb.brier} vs {d.evaluation.baseline_arm_mean.brier} for
              a per-level average — {d.beats_baseline ? 'a statistically significant improvement' : 'no significant improvement yet'}. {d.exploring && 'Exploring means the level has little data, so the bandit is testing it.'}
            </EvalNote>
          </>
        )}
      </Body>
    </Card>
  )
}

export function PredictionsCard({ state }) {
  const hint = { likely: 'good', uncertain: 'warning', 'at risk': 'critical' }
  return (
    <Card title="Predicted quiz scores" subtitle="Gradient boosting on your history" action={<ModelBadge data={state.data} />}>
      <Body state={state}>
        {(d) => (
          <>
            {d.items.length === 0 ? (
              <EmptyState icon={LineChart} title="Nothing to predict yet" message="Enroll in a course to get a score prediction for its quiz." />
            ) : (
              <ul className="divide-y divide-line">
                {d.items.slice(0, 5).map((i) => (
                  <li key={i.quiz_id} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink">{i.course_title}</p>
                      <p className="text-xs text-ink-3">{i.status === 'active' ? 'In progress' : 'Completed'} · {i.previous_attempts} previous attempt{i.previous_attempts === 1 ? '' : 's'}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold tabular-nums text-ink">{Math.round(i.predicted_score)}% <span className="text-xs font-normal text-ink-3">±{Math.round(i.expected_error_mae)}</span></p>
                      <Badge tone={hint[i.pass_probability_hint]}>{i.pass_probability_hint}</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <EvalNote>
              ± is the model's mean absolute error on held-out quizzes ({d.evaluation.gradient_boosting.mae} points vs
              {' '}{d.evaluation.baseline_student_prior_mean.mae} for "your average so far") — {d.beats_baseline ? 'a statistically significant improvement' : 'the difference is not statistically significant'}.
            </EvalNote>
          </>
        )}
      </Body>
    </Card>
  )
}

export function StyleCard({ state }) {
  return (
    <Card title="Learning style" subtitle="Decision tree on profile + behaviour" action={<ModelBadge data={state.data} />}>
      <Body state={state}>
        {(d) => (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-surface-2 p-3">
                <p className="text-xs text-ink-3">Self-reported</p>
                <p className="font-semibold text-ink">{d.self_reported_style || 'Not set'}</p>
              </div>
              <div className="rounded-xl bg-surface-2 p-3">
                <p className="text-xs text-ink-3">Model prediction</p>
                <p className="font-semibold text-ink">{d.predicted_style}</p>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {Object.entries(d.probabilities).sort((a, b) => b[1] - a[1]).map(([style, p]) => (
                <Meter key={style} label={style} value={p} tone="brand" />
              ))}
            </div>
            {!d.reliable && (
              <div className="mt-4 flex gap-2 rounded-xl border border-warning/30 bg-warning-soft p-3 text-xs text-ink-2">
                <AlertTriangle className="size-4 shrink-0 text-warning" aria-hidden />
                <span>{d.advice} (cross-validated accuracy {pct(d.evaluation.cv_accuracy_mean)} vs {pct(d.evaluation.baseline_majority_accuracy)} baseline)</span>
              </div>
            )}
            {d.reliable && <EvalNote><UserSearch className="mr-1 inline size-3.5" aria-hidden />Cross-validated accuracy {pct(d.evaluation.cv_accuracy_mean)}.</EvalNote>}
          </>
        )}
      </Body>
    </Card>
  )
}
