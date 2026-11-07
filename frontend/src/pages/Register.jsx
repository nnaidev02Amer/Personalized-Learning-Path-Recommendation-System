import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { UserPlus } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Button from '../components/ui/Button'
import { TextInput } from '../components/ui/Form'
import { Notice, Skeleton } from '../components/ui/States'
import StudentForm, { toPayload, validateStudent } from '../components/profile/StudentForm'
import { AuthShell } from './Login'

export default function Register() {
  const { status, register } = useAuth()
  const navigate = useNavigate()
  const [config, setConfig] = useState(null)
  const [values, setValues] = useState(null)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState(null)
  const blank = useMemo(() => ({}), [])
  const onChange = useCallback((v) => setValues(v), [])

  useEffect(() => {
    api.auth.config().then(setConfig).catch(() => setConfig({ allow_self_registration: false }))
  }, [])

  if (status === 'authenticated') return <Navigate to="/" replace />
  if (!config) return <AuthShell title="Create account"><Skeleton className="h-48 w-full" /></AuthShell>
  if (!config.allow_self_registration) {
    return (
      <AuthShell title="Registration is closed" footer={<Link to="/login" className="font-medium text-brand hover:underline">Back to sign in</Link>}>
        <Notice title="Ask an administrator">Student accounts are created by an administrator for this installation.</Notice>
      </AuthShell>
    )
  }

  const submit = async (e) => {
    e.preventDefault()
    setFormError(null)
    const local = validateStudent(values)
    if (password !== confirm) local.confirm = 'Passwords do not match'
    if (password.length < 10) local.password = 'Use at least 10 characters'
    setErrors(local)
    if (Object.keys(local).length) return
    setBusy(true)
    try {
      await register({ ...toPayload(values), password })
      navigate('/', { replace: true })
    } catch (err) {
      setErrors(err.code === 'email_taken' ? { email: err.message } : err.fieldErrors)
      setFormError(err.status === 422 ? 'Please fix the highlighted fields.' : err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Create a student account" subtitle="You get your own learner profile, courses and recommendations."
               footer={<>Already registered? <Link to="/login" className="font-medium text-brand hover:underline">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <StudentForm initial={blank} errors={errors} onChange={onChange} disabled={busy} />
        <TextInput label="Password" type="password" autoComplete="new-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} error={errors.password} disabled={busy}
                   hint="At least 10 characters; not your name or e-mail." />
        <TextInput label="Repeat password" type="password" autoComplete="new-password" value={confirm}
                   onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} disabled={busy} />
        {formError && <p role="alert" className="rounded-lg bg-critical-soft px-3 py-2 text-sm text-critical">{formError}</p>}
        <Button type="submit" icon={UserPlus} loading={busy} className="w-full">Create account</Button>
      </form>
    </AuthShell>
  )
}
