import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from './AuthContext'

const StudentContext = createContext(null)
/**
 * Holds the student whose data the pages show.
 *  - A signed-in STUDENT always sees their own profile (the id comes from the session, never from the browser).
 *  - An ADMINISTRATOR has no student context: they use the administration pages only.
 * `version` increases after any mutation so pages can refetch dependent data.
 */
export function StudentProvider({ children }) {
  const { user, isStudent } = useAuth()
  const studentId = isStudent ? user.student_id : null     // always the session's own student, never a browser value
  const [student, setStudent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [version, setVersion] = useState(0)

  const setStudentId = useCallback(() => {}, [])         // kept for existing callers; the student is fixed by the session

  const load = useCallback(async () => {
    if (!isStudent || !studentId) {                          // signed out, or an administrator: no student data at all
      setStudent(null)
      setError(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    setStudent((s) => (s && s.id === studentId ? s : null))      // never show the previous user's profile
    try {
      setStudent(await api.students.get(studentId))
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }, [studentId, isStudent])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {                                           // another account (or none): forget the previous one
    setVersion(0)
  }, [user?.id])

  const refresh = useCallback(() => {
    setVersion((v) => v + 1)
  }, [])

  const value = useMemo(
    () => ({ studentId: student?.id ?? null, student, setStudent, setStudentId, loading, error,
      reload: load, version, refresh }),
    [student, setStudentId, loading, error, load, version, refresh],
  )
  return <StudentContext.Provider value={value}>{children}</StudentContext.Provider>
}

export function useStudent() {
  return useContext(StudentContext)
}
