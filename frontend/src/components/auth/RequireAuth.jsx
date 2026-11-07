import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { PageSkeleton } from '../ui/States'

/**
 * Route guard. Anonymous visitors go to /login (remembering where they were heading). With `role="admin"` or
 * `role="student"` a signed-in user of the other role is sent to their own dashboard ("/").
 * The API enforces the same rules on every request -- this only keeps the interface honest.
 */
export default function RequireAuth({ role, children }) {
  const { status, isAdmin, isStudent } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <div className="p-6"><PageSkeleton /></div>
  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  if ((role === 'admin' && !isAdmin) || (role === 'student' && !isStudent)) return <Navigate to="/" replace />
  return children
}
