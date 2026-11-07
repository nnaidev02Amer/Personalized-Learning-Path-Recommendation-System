import { LogOut, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import Badge from '../ui/Badge'
import { Avatar } from './StudentSwitcher'

/** Who is signed in, their role, and the sign-out button. */
export default function UserMenu() {
  const { user, student, isAdmin, logout } = useAuth()
  const navigate = useNavigate()
  const name = student?.name || user?.email || ''
  const signOut = async () => {
    await logout()
    navigate('/login', { replace: true })
  }
  return (
    <div className="flex items-center gap-2">
      <div className="hidden items-center gap-2 md:flex">
        <Avatar name={name} size="sm" />
        <span className="max-w-[10rem] truncate text-sm text-ink-2" title={user?.email}>{isAdmin ? user?.email : name}</span>
        {isAdmin && <Badge tone="brand" icon={ShieldCheck}>Admin</Badge>}
      </div>
      <button onClick={signOut} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-sm text-ink-2 hover:bg-surface-2"
              aria-label="Sign out">
        <LogOut className="size-4" aria-hidden />
        <span className="hidden sm:inline">Sign out</span>
      </button>
    </div>
  )
}
