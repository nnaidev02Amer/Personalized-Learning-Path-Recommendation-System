import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, setCsrfToken, UNAUTHORIZED_EVENT } from '../api/client'

const AuthContext = createContext(null)

/**
 * The signed-in user. The session itself lives in an HttpOnly cookie the page cannot read; the page only
 * keeps the CSRF token (in memory) and the user's identity. Status: 'loading' | 'anonymous' | 'authenticated'.
 */
export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: 'loading', user: null, student: null, error: null })

  const apply = useCallback((session) => {
    setCsrfToken(session?.csrf_token)
    setState(session
      ? { status: 'authenticated', user: session.user, student: session.student, error: null }
      : { status: 'anonymous', user: null, student: null, error: null })
  }, [])

  useEffect(() => {
    let alive = true
    api.auth.me()
      .then((session) => alive && apply(session))
      .catch((error) => {
        if (!alive) return
        // 401 = simply not signed in; anything else (API offline) is shown on the sign-in page.
        apply(null)
        if (error.status !== 401) setState((s) => ({ ...s, error }))
      })
    return () => { alive = false }
  }, [apply])

  useEffect(() => {
    const onExpired = () => apply(null)
    window.addEventListener(UNAUTHORIZED_EVENT, onExpired)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onExpired)
  }, [apply])

  /** `portal` ('admin' | 'student') makes the sign-in page refuse an account of the other role BEFORE any session is kept. */
  const login = useCallback(async (email, password, portal) => {
    const session = await api.auth.login(email, password)
    if (portal && (session.user.role === 'admin') !== (portal === 'admin')) {
      setCsrfToken(session.csrf_token)
      try { await api.auth.logout() } catch { /* the session is discarded either way */ }
      setCsrfToken(null)
      const err = new Error(portal === 'admin'
        ? 'This is not an administrator account. Use the student sign-in.'
        : 'This is an administrator account. Use the Admin Login.')
      err.code = 'wrong_portal'
      throw err
    }
    apply(session)
    return session
  }, [apply])

  const register = useCallback(async (data) => {
    const session = await api.auth.register(data)
    apply(session)
    return session
  }, [apply])

  const logout = useCallback(async () => {
    try {
      await api.auth.logout()
    } catch {
      // the server may already have dropped the session; either way we are signed out locally
    }
    try {
      localStorage.removeItem('currentStudentId')
    } catch {
      // storage unavailable
    }
    apply(null)
  }, [apply])

  const value = useMemo(() => ({
    ...state,
    isAdmin: state.user?.role === 'admin',
    isStudent: state.user?.role === 'student',
    login, register, logout,
  }), [state, login, register, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
