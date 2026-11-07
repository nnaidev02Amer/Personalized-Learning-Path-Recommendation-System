import { useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { GraduationCap, LogIn, ShieldCheck } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { Card } from '../components/ui/Card'
import Button from '../components/ui/Button'
import { TextInput } from '../components/ui/Form'
import { ErrorState } from '../components/ui/States'

export function AuthShell({ title, subtitle, children, footer }) {
  return (
    <main className="grid min-h-full place-items-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="grid size-10 place-items-center rounded-xl bg-brand text-white">
            <GraduationCap className="size-5" aria-hidden />
          </span>
          <div>
            <p className="text-base font-semibold leading-tight text-ink">PathWise</p>
            <p className="text-xs leading-tight text-ink-3">Personalized learning</p>
          </div>
        </div>
        <Card title={title} subtitle={subtitle}>{children}</Card>
        {footer && <p className="mt-4 text-center text-sm text-ink-3">{footer}</p>}
      </div>
    </main>
  )
}

/** Where to go after sign-in: the page the visitor asked for, if their role may open it; otherwise their dashboard. */
export function landingFor(role, from) {
  const adminOnly = from === '/models' || from?.startsWith('/admin')
  if (!from || from === '/login' || from === '/register' || from === '/admin/login') return '/'
  return (role === 'admin') === Boolean(adminOnly) ? from : '/'
}

export default function Login() {
  const { status, user, login, error: startupError } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const adminMode = location.pathname === '/admin/login'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [config, setConfig] = useState(null)

  useEffect(() => {
    api.auth.config().then(setConfig).catch(() => setConfig({ allow_self_registration: false }))
  }, [])

  if (status === 'authenticated') {
    return <Navigate to={landingFor(user.role, location.state?.from)} replace />
  }
  if (startupError) return <div className="p-6"><ErrorState error={startupError} onRetry={() => window.location.reload()} /></div>

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!email.trim() || !password) return setError('Enter your e-mail and password.')
    setBusy(true)
    try {
      const session = await login(email.trim(), password, adminMode ? 'admin' : 'student')
      navigate(landingFor(session.user.role, location.state?.from), { replace: true })
    } catch (err) {
      setError(err.status === 401 ? 'Incorrect e-mail or password.' : err.message)    // includes the wrong-portal message
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title={adminMode ? 'Admin login' : 'Student sign in'}
               subtitle={adminMode ? 'Administrator access only.' : 'Sign in to continue your learning path.'}
               footer={adminMode
                 ? <Link to="/login" className="font-medium text-brand hover:underline">Back to student sign in</Link>
                 : <>{config?.allow_self_registration
                   ? <>New student? <Link to="/register" className="font-medium text-brand hover:underline">Create an account</Link></>
                   : 'Need an account? Ask an administrator.'}
                   {' · '}<Link to="/admin/login" className="inline-flex items-center gap-1 font-medium text-brand hover:underline"><ShieldCheck className="size-3.5" aria-hidden />Admin login</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="E-mail" type="email" autoComplete="username" value={email} autoFocus
                   onChange={(e) => setEmail(e.target.value)} disabled={busy} />
        <TextInput label="Password" type="password" autoComplete="current-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} disabled={busy} />
        {error && <p role="alert" className="rounded-lg bg-critical-soft px-3 py-2 text-sm text-critical">{error}</p>}
        <Button type="submit" icon={LogIn} loading={busy} className="w-full">{adminMode ? 'Sign in as administrator' : 'Sign in'}</Button>
      </form>
    </AuthShell>
  )
}
