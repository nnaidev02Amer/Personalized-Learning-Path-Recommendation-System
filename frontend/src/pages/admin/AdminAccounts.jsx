import { useCallback, useMemo, useState } from 'react'
import { KeyRound, LogOut, Search, ShieldCheck, Unlock, UserCheck, UserPlus, UserX } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import PageHeader from '../../components/ui/PageHeader'
import { Card } from '../../components/ui/Card'
import Badge from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import { Select, TextInput } from '../../components/ui/Form'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui/States'
import StudentForm, { toPayload, validateStudent } from '../../components/profile/StudentForm'
import { formatDate } from '../../utils/format'

const PAGE = 15

function CreateAccountModal({ open, onClose, onCreated }) {
  const toast = useToast()
  const [values, setValues] = useState(null)
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const blank = useMemo(() => ({}), [])
  const onChange = useCallback((v) => setValues(v), [])

  const submit = async () => {
    const local = validateStudent(values)
    if (password.length < 10) local.password = 'Use at least 10 characters'
    setErrors(local)
    if (Object.keys(local).length) return
    setBusy(true)
    try {
      const created = await api.admin.createUser({ ...toPayload(values), password })
      toast.success('Account created', `${created.student_name} can sign in with ${created.email}.`)
      setPassword('')
      onCreated()
    } catch (e) {
      setErrors(e.code === 'email_taken' ? { email: e.message } : e.fieldErrors)
      toast.error('Could not create the account', e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="New student account" size="lg"
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
             <Button icon={UserPlus} loading={busy} onClick={submit}>Create account</Button></>}>
      <div className="space-y-4">
        <StudentForm initial={blank} errors={errors} onChange={onChange} disabled={busy} />
        <TextInput label="Temporary password" type="password" autoComplete="new-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} error={errors.password}
                   hint="At least 10 characters; not the student's name or e-mail. Share it securely." />
      </div>
    </Modal>
  )
}

function ResetPasswordModal({ user, onClose, onDone }) {
  const toast = useToast()
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.admin.updateUser(user.id, { password })
      toast.success('Password reset', 'The user was signed out everywhere.')
      setPassword('')
      onDone()
    } catch (e) {
      setError(e.fieldErrors?.password || e.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={Boolean(user)} onClose={onClose} title={`Reset password — ${user?.email || ''}`}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
             <Button icon={KeyRound} loading={busy} onClick={submit}>Reset password</Button></>}>
      <TextInput label="New password" type="password" autoComplete="new-password" value={password}
                 onChange={(e) => setPassword(e.target.value)} error={error} hint="Existing sessions of this user end immediately." />
    </Modal>
  )
}

export default function AdminAccounts() {
  const { user: me } = useAuth()
  const toast = useToast()
  const [query, setQuery] = useState('')
  const [role, setRole] = useState('')
  const [offset, setOffset] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [resetFor, setResetFor] = useState(null)
  const search = useDebounced(query)
  const list = useApi(() => api.admin.users({ search, role: role || undefined, limit: PAGE, offset }), [search, role, offset])

  const act = async (fn, success) => {
    try {
      await fn()
      toast.success(success)
      list.reload()
    } catch (e) {
      toast.error('Action failed', e.message)
    }
  }
  const data = list.data

  return (
    <div className="space-y-6">
      <PageHeader title="Accounts" description="Sign-in accounts for students and administrators."
                  actions={<Button icon={UserPlus} onClick={() => setCreateOpen(true)}>New student account</Button>} />
      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label className="flex min-w-[14rem] flex-1 items-center gap-2 rounded-lg border border-line px-2.5">
            <Search className="size-4 text-ink-3" aria-hidden />
            <input value={query} onChange={(e) => { setQuery(e.target.value); setOffset(0) }} placeholder="Search e-mail…"
                   aria-label="Search accounts" className="h-9 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-3" />
          </label>
          <div className="w-40">
            <Select value={role} onChange={(e) => { setRole(e.target.value); setOffset(0) }} placeholder="All roles"
                    options={['admin', 'student']} aria-label="Filter by role" />
          </div>
        </div>

        {list.error ? <ErrorState compact error={list.error} onRetry={list.reload} /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-ink-3">
                <tr><th className="py-2 pr-3">Account</th><th className="px-3">Role</th><th className="px-3">Status</th>
                  <th className="px-3">Last sign-in</th><th className="pl-3 text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {list.loading && !data && Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i}><td colSpan={5} className="py-3"><Skeleton className="h-6 w-full" /></td></tr>))}
                {data?.items.map((u) => (
                  <tr key={u.id}>
                    <td className="py-2.5 pr-3">
                      <p className="font-medium text-ink">{u.email}</p>
                      <p className="text-xs text-ink-3">{u.student_name ? `${u.student_name} · student #${u.student_id}` : 'administrator'}</p>
                    </td>
                    <td className="px-3">{u.role === 'admin' ? <Badge tone="brand" icon={ShieldCheck}>admin</Badge> : <Badge>student</Badge>}</td>
                    <td className="px-3">
                      <div className="flex flex-wrap gap-1">
                        {u.is_active ? <Badge tone="good">active</Badge> : <Badge tone="critical">disabled</Badge>}
                        {u.locked && <Badge tone="warning">locked</Badge>}
                        {u.active_sessions > 0 && <Badge>{u.active_sessions} session{u.active_sessions > 1 ? 's' : ''}</Badge>}
                      </div>
                    </td>
                    <td className="px-3 text-ink-2">{u.last_login_at ? formatDate(u.last_login_at) : 'never'}</td>
                    <td className="pl-3">
                      <div className="flex flex-wrap justify-end gap-1.5">
                        <Button size="sm" variant="secondary" icon={KeyRound} onClick={() => setResetFor(u)}>Reset</Button>
                        {u.locked && <Button size="sm" variant="secondary" icon={Unlock}
                          onClick={() => act(() => api.admin.updateUser(u.id, { unlock: true }), 'Account unlocked')}>Unlock</Button>}
                        {u.active_sessions > 0 && <Button size="sm" variant="secondary" icon={LogOut}
                          onClick={() => act(() => api.admin.revokeSessions(u.id), 'Signed out everywhere')}>Sign out</Button>}
                        {u.id !== me.id && (u.is_active
                          ? <Button size="sm" variant="danger-outline" icon={UserX}
                              onClick={() => act(() => api.admin.updateUser(u.id, { is_active: false }), 'Account disabled')}>Disable</Button>
                          : <Button size="sm" variant="secondary" icon={UserCheck}
                              onClick={() => act(() => api.admin.updateUser(u.id, { is_active: true }), 'Account enabled')}>Enable</Button>)}
                      </div>
                    </td>
                  </tr>
                ))}
                {data && data.items.length === 0 && <tr><td colSpan={5}><EmptyState title="No accounts match" /></td></tr>}
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
        <p className="mt-4 text-xs text-ink-3">Seeded sample learners have no login until you create one on the Students page.
          Administrators are created from the command line (<code>python -m backend.app.create_admin</code>).</p>
      </Card>

      <CreateAccountModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); list.reload() }} />
      <ResetPasswordModal user={resetFor} onClose={() => setResetFor(null)} onDone={() => { setResetFor(null); list.reload() }} />
    </div>
  )
}
