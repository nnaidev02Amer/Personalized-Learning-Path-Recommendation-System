import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Menu, Moon, Sun } from 'lucide-react'
import { api } from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { useStudent } from '../../context/StudentContext'
import { useTheme } from '../../context/ThemeContext'
import { ErrorState, PageSkeleton, EmptyState } from '../ui/States'
import Sidebar from './Sidebar'
import UserMenu from './UserMenu'

function ApiStatus() {
  const [ok, setOk] = useState(null)
  useEffect(() => {
    let alive = true
    const check = () => api.health().then(() => alive && setOk(true)).catch(() => alive && setOk(false))
    check()
    const t = setInterval(check, 30000)
    return () => { alive = false; clearInterval(t) }
  }, [])
  const label = ok == null ? 'Checking API…' : ok ? 'API connected' : 'API offline'
  return (
    <span className="hidden items-center gap-2 text-xs text-ink-3 md:flex" title={label}>
      <span className={`size-2 rounded-full ${ok == null ? 'bg-ink-3' : ok ? 'bg-good' : 'bg-critical'}`} aria-hidden />
      {label}
    </span>
  )
}

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { theme, toggle } = useTheme()
  const { student, loading, error, reload } = useStudent()
  const { isAdmin } = useAuth()
  const location = useLocation()

  // Block body: in current Chromium, scrollTo() returns a Promise, which must not be returned from an effect.
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])

  // Administration pages never load a student; student pages show the signed-in student's own data.
  let content = <Outlet />
  if (!isAdmin) {
    if (loading && !student) content = <PageSkeleton />
    else if (error && !student) content = <ErrorState error={error} onRetry={reload} />
    else if (!student) {
      content = <EmptyState title="No learner profile" message="Your account is not linked to a student profile. Ask an administrator." />
    }
  }

  return (
    <div className="min-h-full">
      <Sidebar mobileOpen={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur sm:px-6">
          <button onClick={() => setMenuOpen(true)} className="rounded-lg p-2 text-ink-2 hover:bg-surface-2 lg:hidden" aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <ApiStatus />
          <div className="ml-auto flex items-center gap-2">
            <button onClick={toggle} className="rounded-lg p-2 text-ink-2 hover:bg-surface-2"
                    aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>
              {theme === 'dark' ? <Sun className="size-5" /> : <Moon className="size-5" />}
            </button>
            <UserMenu />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:py-8">{content}</main>
      </div>
    </div>
  )
}
