import { useState } from 'react'
import { AlertTriangle, KeyRound, ListChecks, Search, Trash2, UserPlus } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useToast } from '../../context/ToastContext'
import PageHeader from '../../components/ui/PageHeader'
import { Card } from '../../components/ui/Card'
import Badge from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import ProgressBar from '../../components/ui/ProgressBar'
import { TextInput } from '../../components/ui/Form'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui/States'
import { formatDate } from '../../utils/format'

const PAGE = 15

function EnrolmentsModal({ student, onClose }) {
  const enrolments = useApi(student ? () => api.enrollments.list(student.id) : null, [student?.id])
  return (
    <Modal open={Boolean(student)} onClose={onClose} title={`${student?.name || ''} — course enrolments`} size="lg"
           footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      {enrolments.loading || !enrolments.data ? (enrolments.error ? <ErrorState compact error={enrolments.error} /> : <Skeleton className="h-24 w-full" />) :
        enrolments.data.length === 0 ? <EmptyState title="Not enrolled in any course" /> : (
          <ul className="divide-y divide-line">
            {enrolments.data.map((e) => (
              <li key={e.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-ink">{e.course.title} <span className="text-xs text-ink-3">{e.course.code}</span></p>
                  <Badge tone={e.status === 'completed' ? 'good' : e.status === 'dropped' ? 'neutral' : 'brand'}>{e.status}</Badge>
                </div>
                <div className="mt-2 flex items-center gap-3">
                  <div className="flex-1"><ProgressBar value={e.progress} /></div>
                  <span className="text-xs text-ink-3">{e.completed_lessons}/{e.total_lessons} lessons · since {formatDate(e.enrolled_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
    </Modal>
  )
}

function LoginModal({ student, onClose, onDone }) {
  const toast = useToast()
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.admin.linkAccount(student.id, password)
      toast.success('Login created', `${student.name} can now sign in with ${student.email}.`)
      setPassword('')
      onDone()
    } catch (e) {
      setError(e.fieldErrors?.password || e.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={Boolean(student)} onClose={onClose} title={`Create a login for ${student?.name || ''}`}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
             <Button icon={KeyRound} loading={busy} onClick={submit}>Create login</Button></>}>
      <p className="mb-4 text-sm text-ink-2">This attaches a login to the <strong className="text-ink">existing</strong> learner
        profile (no new student is created). Their sign-in e-mail is <strong className="text-ink">{student?.email}</strong>.</p>
      <TextInput label="Temporary password" type="password" autoComplete="new-password" value={password}
                 onChange={(e) => setPassword(e.target.value)} error={error} hint="At least 10 characters. Share it securely." />
    </Modal>
  )
}

export default function AdminStudents() {
  const toast = useToast()
  const [query, setQuery] = useState('')
  const [atRisk, setAtRisk] = useState(false)
  const [offset, setOffset] = useState(0)
  const [enrolFor, setEnrolFor] = useState(null)
  const [loginFor, setLoginFor] = useState(null)
  const [deleteFor, setDeleteFor] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const search = useDebounced(query)

  const list = useApi(() => api.admin.students({ search, at_risk: atRisk || undefined, limit: PAGE, offset }),
    [search, atRisk, offset])

  const remove = async () => {
    setDeleting(true)
    try {
      await api.students.remove(deleteFor.id)
      toast.success('Student deleted', `${deleteFor.name} and their history were removed.`)
      setDeleteFor(null)
      list.reload()
    } catch (e) {
      toast.error('Could not delete student', e.message)
    } finally {
      setDeleting(false)
    }
  }

  const data = list.data
  return (
    <div className="space-y-6">
      <PageHeader title="Students" description="Every learner, with enrolments and performance."
                  actions={<Button to="/admin/accounts" icon={UserPlus}>New student account</Button>} />
      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label className="flex min-w-[14rem] flex-1 items-center gap-2 rounded-lg border border-line px-2.5">
            <Search className="size-4 text-ink-3" aria-hidden />
            <input value={query} onChange={(e) => { setQuery(e.target.value); setOffset(0) }} placeholder="Search name or e-mail…"
                   aria-label="Search students" className="h-9 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-3" />
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-2">
            <input type="checkbox" checked={atRisk} onChange={(e) => { setAtRisk(e.target.checked); setOffset(0) }} />
            At-risk only
          </label>
        </div>

        {list.error ? <ErrorState compact error={list.error} onRetry={list.reload} /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-ink-3">
                <tr><th className="py-2 pr-3">Student</th><th className="px-3">Courses</th><th className="px-3">Attempts</th>
                  <th className="px-3">Avg score</th><th className="px-3">Login</th><th className="pl-3 text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {list.loading && !data && Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}><td colSpan={6} className="py-3"><Skeleton className="h-6 w-full" /></td></tr>))}
                {data?.items.map((s) => (
                  <tr key={s.id}>
                    <td className="py-2.5 pr-3">
                      <p className="font-medium text-ink">{s.name} {s.is_synthetic && <Badge tone="warning" className="ml-1">seeded</Badge>}</p>
                      <p className="text-xs text-ink-3">#{s.id} · {s.email}</p>
                    </td>
                    <td className="px-3 tabular-nums text-ink-2">{s.active_enrollments} active · {s.completed_enrollments} done</td>
                    <td className="px-3 tabular-nums text-ink-2">{s.quiz_attempts}</td>
                    <td className="px-3 tabular-nums">
                      {s.average_score == null ? <span className="text-ink-3">—</span> : (
                        <span className={s.at_risk ? 'font-medium text-warning' : 'text-ink-2'}>
                          {s.at_risk && <AlertTriangle className="mr-1 inline size-3.5" aria-label="at risk" />}{s.average_score}%</span>)}
                    </td>
                    <td className="px-3">{s.has_login ? <Badge tone="good">has login</Badge> : <Badge>none</Badge>}</td>
                    <td className="pl-3">
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="secondary" icon={ListChecks} onClick={() => setEnrolFor(s)} aria-label={`Enrolments of ${s.name}`}>Courses</Button>
                        {!s.has_login && <Button size="sm" variant="secondary" icon={KeyRound} onClick={() => setLoginFor(s)}>Login</Button>}
                        <Button size="sm" variant="danger-outline" icon={Trash2} onClick={() => setDeleteFor(s)} aria-label={`Delete ${s.name}`} />
                      </div>
                    </td>
                  </tr>
                ))}
                {data && data.items.length === 0 && (
                  <tr><td colSpan={6}><EmptyState title="No students match" /></td></tr>)}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > PAGE && (
          <div className="mt-4 flex items-center justify-between text-sm text-ink-3">
            <span>{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
              <Button size="sm" variant="secondary" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <EnrolmentsModal student={enrolFor} onClose={() => setEnrolFor(null)} />
      <LoginModal student={loginFor} onClose={() => setLoginFor(null)} onDone={() => { setLoginFor(null); list.reload() }} />
      <Modal open={Boolean(deleteFor)} onClose={() => setDeleteFor(null)} title="Delete student?"
             footer={<><Button variant="secondary" onClick={() => setDeleteFor(null)}>Cancel</Button>
               <Button variant="danger" icon={Trash2} loading={deleting} onClick={remove}>Delete permanently</Button></>}>
        <p className="text-sm text-ink-2">This permanently deletes <strong className="text-ink">{deleteFor?.name}</strong>, their login,
          enrolments, quiz attempts and activity. This cannot be undone.</p>
        {deleteFor?.is_synthetic && <p className="mt-3 text-sm text-warning">This is a seeded sample learner; the models were trained with their history.</p>}
      </Modal>
    </div>
  )
}
