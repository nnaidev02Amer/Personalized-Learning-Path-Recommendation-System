import { useState } from 'react'
import { CheckCircle2, MinusCircle, RefreshCw, XCircle } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useToast } from '../context/ToastContext'
import PageHeader from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Tabs from '../components/ui/Tabs'
import { ErrorState, Notice, PageSkeleton } from '../components/ui/States'
import { formatDate } from '../utils/format'

/** Verdict from a paired-bootstrap comparison: significant win / significant loss / no difference. */
function Verdict({ cmp, against = 'baseline' }) {
  if (!cmp) return null
  const [lo, hi] = cmp.ci95
  if (lo > 0) return <Badge tone="good" icon={CheckCircle2}>Significantly better than {against}</Badge>
  if (hi < 0) return <Badge tone="critical" icon={XCircle}>Significantly worse than {against}</Badge>
  return <Badge icon={MinusCircle}>No significant difference from {against}</Badge>
}

function MetricTable({ columns, rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[28rem] text-left text-sm">
        <thead className="text-xs text-ink-3">
          <tr>{columns.map((c) => <th key={c.key} className="py-2 pr-4 font-medium">{c.label}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.name} className={r.highlight ? 'font-medium text-ink' : 'text-ink-2'}>
              {columns.map((c) => <td key={c.key} className="py-2 pr-4 tabular-nums">{r[c.key] ?? '—'}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const ci = (c) => c && `${c.improvement > 0 ? '+' : ''}${c.improvement} [${c.ci95[0]}, ${c.ci95[1]}]`
const NAMES = {
  hybrid: 'Hybrid', content: 'Content-based', collaborative: 'Collaborative (item-kNN)',
  popularity: 'Popularity (baseline)', random: 'Random (baseline)',
}

function Recommendations({ r }) {
  const [protocol, setProtocol] = useState('unlocked_courses')
  const p = r.protocols[protocol]
  const rows = Object.entries(p.methods).map(([m, v]) => ({
    name: NAMES[m], ndcg: v.ndcg_at_k, hit: v.hit_rate_at_k, mrr: v.mrr,
    cov: v.catalog_coverage == null ? '—' : `${Math.round(v.catalog_coverage * 100)}%`,
    delta: ci(p.vs_popularity_ndcg[m]), highlight: m === 'hybrid',
  }))
  return (
    <Card title="Course recommendations" subtitle={r.protocol}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs label="Protocol" value={protocol} onChange={setProtocol} tabs={[
          { value: 'unlocked_courses', label: 'Unlocked courses' }, { value: 'all_untaken_courses', label: 'All untaken courses' }]} />
        <span className="text-xs text-ink-3">{r.students_test} test students · {p.mean_candidates} candidates on average · k = {r.k}</span>
      </div>
      <MetricTable rows={rows} columns={[
        { key: 'name', label: 'Method' }, { key: 'ndcg', label: `NDCG@${r.k}` }, { key: 'hit', label: `HR@${r.k}` },
        { key: 'mrr', label: 'MRR' }, { key: 'cov', label: 'Coverage' }, { key: 'delta', label: 'NDCG Δ vs popularity [95% CI]' }]} />
      <div className="mt-4 flex flex-wrap gap-2">
        {['hybrid', 'collaborative', 'content'].map((m) => (
          <span key={m} className="flex items-center gap-2 text-xs text-ink-3">{NAMES[m]}: <Verdict cmp={p.vs_popularity_ndcg[m]} against="popularity" /></span>
        ))}
      </div>
      <p className="mt-3 text-xs text-ink-3">Tuned hybrid weight α = {r.tuned_params.alpha} (on the tuning half). With few unlocked candidates, hit rate is close to 1 for every method; NDCG and MRR are the informative metrics.</p>
    </Card>
  )
}

function Simple({ title, subtitle, rows, metrics, verdict, footer }) {
  return (
    <Card title={title} subtitle={subtitle} action={verdict}>
      <MetricTable rows={rows} columns={[{ key: 'name', label: 'Model' }, ...metrics]} />
      {footer && <p className="mt-3 text-xs text-ink-3">{footer}</p>}
    </Card>
  )
}

export default function ModelEvaluation() {
  const toast = useToast()
  const report = useApi(() => api.ai.evaluation(), [])
  const [busy, setBusy] = useState(false)

  const retrain = async () => {
    setBusy(true)
    try {
      const r = await api.ai.retrain()
      toast.success('Models retrained', `Finished in ${r.training_seconds}s using the current database.`)
      report.reload()
    } catch (e) {
      toast.error('Retraining failed', e.message)
    } finally {
      setBusy(false)
    }
  }

  if (report.loading && !report.data) return <PageSkeleton cards={2} />
  if (report.error) return <ErrorState error={report.error} onRetry={report.reload} />
  const r = report.data
  const kt = r.knowledge_tracing
  const pp = r.performance_prediction
  const ad = r.adaptive_difficulty
  const ls = r.learning_style
  const label = (k) => k.replace('baseline_', 'Baseline: ').replace(/_/g, ' ')

  return (
    <div className="space-y-6">
      <PageHeader title="Model Evaluation" description={`Measured on held-out data · trained ${formatDate(r.trained_at, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} in ${r.training_seconds}s`}
                  actions={<Button icon={RefreshCw} loading={busy} onClick={retrain}>Retrain on current data</Button>} />
      <Notice tone="warning" title="Read these numbers with the data in mind">
        {r.training_data.note} {r.training_data.real_students} of {r.training_data.students} students were created in this app.
        Comparisons use a paired bootstrap 95% confidence interval; a model only counts as better when the whole interval is above zero.
      </Notice>

      <Recommendations r={r.recommendations} />

      <div className="grid gap-6 xl:grid-cols-2">
        <Simple title="Skill mastery — Bayesian Knowledge Tracing" subtitle={kt.protocol}
                verdict={<Verdict cmp={kt.vs_best_baseline_log_loss} />}
                rows={Object.entries(kt.results).map(([k, v]) => ({ name: k === 'bkt' ? 'BKT' : label(k), auc: v.auc ?? '—', ll: v.log_loss, brier: v.brier, highlight: k === 'bkt' }))}
                metrics={[{ key: 'auc', label: 'AUC' }, { key: 'll', label: 'Log-loss' }, { key: 'brier', label: 'Brier' }]}
                footer={`Fitted parameters: P(init) ${kt.params.p_init}, P(learn) ${kt.params.p_learn}, P(slip) ${kt.params.p_slip}, P(guess) ${kt.params.p_guess}. ${kt.test_observations} test answers from ${kt.test_students} students. Log-loss Δ vs ${label(kt.best_baseline)}: ${ci(kt.vs_best_baseline_log_loss)}.`} />
        <Simple title="Performance prediction — gradient boosting" subtitle={pp.protocol}
                verdict={<Verdict cmp={pp.vs_best_baseline_abs_error} />}
                rows={Object.entries(pp.results).map(([k, v]) => ({ name: k === 'gradient_boosting' ? 'Gradient boosting' : label(k), mae: v.mae, rmse: v.rmse, r2: v.r2, highlight: k === 'gradient_boosting' }))}
                metrics={[{ key: 'mae', label: 'MAE (points)' }, { key: 'rmse', label: 'RMSE' }, { key: 'r2', label: 'R²' }]}
                footer={`${pp.test_attempts} test attempts after ${formatDate(pp.cutoff)}. MAE Δ vs ${label(pp.best_baseline)}: ${ci(pp.vs_best_baseline_abs_error)}. Top features: ${Object.keys(pp.feature_importance).slice(0, 3).join(', ').replace(/_/g, ' ')}.`} />
        <Simple title="Adaptive difficulty — LinUCB bandit" subtitle={ad.protocol}
                verdict={<Verdict cmp={ad.vs_arm_mean_brier} />}
                rows={Object.entries(ad.reward_model).map(([k, v]) => ({ name: k === 'linucb' ? 'LinUCB reward model' : label(k), brier: v.brier, acc: `${Math.round(v.accuracy * 100)}%`, highlight: k === 'linucb' }))}
                metrics={[{ key: 'brier', label: 'Brier' }, { key: 'acc', label: 'Accuracy' }]}
                footer={`Replay estimate: ${ad.replay.policy_reward_on_matched ?? '—'} reward on ${ad.replay.matched_events} matched events vs ${ad.replay.logged_reward} logged (${ad.replay.note}). Training levels: ${Object.entries(ad.arm_counts_train).map(([k, v]) => `${k} ${v}`).join(', ')}.`} />
        <Simple title="Learning style — decision tree" subtitle={ls.protocol}
                verdict={ls.reliable ? <Badge tone="good" icon={CheckCircle2}>Reliable</Badge> : <Badge tone="critical" icon={XCircle}>Not reliable</Badge>}
                rows={[{ name: 'Decision tree', acc: `${Math.round(ls.cv_accuracy_mean * 100)}% ± ${Math.round(ls.cv_accuracy_std * 100)}`, highlight: true },
                  { name: 'Baseline: majority class', acc: `${Math.round(ls.baseline_majority_accuracy * 100)}%` },
                  { name: 'Chance (4 styles)', acc: `${Math.round(ls.chance_accuracy * 100)}%` }]}
                metrics={[{ key: 'acc', label: 'Cross-validated accuracy' }]}
                footer={ls.reliable
                  ? `Evaluated on ${ls.students} students with a labelled learning style.`
                  : `Not better than always guessing the most common style on ${ls.students} students, so the app uses the self-reported style. (The Phase 1 analysis found the original sample_data.csv labels statistically independent of every recorded feature.)`} />
      </div>
    </div>
  )
}
