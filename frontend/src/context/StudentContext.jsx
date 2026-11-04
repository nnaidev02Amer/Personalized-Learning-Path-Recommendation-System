import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

const StudentContext = createContext(null)
const STORAGE_KEY = 'currentStudentId'

function savedId() {
  try {
    const id = Number(localStorage.getItem(STORAGE_KEY))
    return Number.isInteger(id) && id > 0 ? id : null
  } catch {
    return null
  }
}

/**
 * Holds the student whose dashboard is being viewed (there is no login yet;
 * the switcher in the top bar picks the student). `version` increases after
 * any mutation so pages can refetch dependent data.
 */
export function StudentProvider({ children }) {
  const [studentId, setStudentIdState] = useState(savedId)
  const [student, setStudent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [version, setVersion] = useState(0)

  const setStudentId = useCallback((id) => {
    setStudentIdState(id)
    try {
      localStorage.setItem(STORAGE_KEY, String(id))
    } catch {
      // storage unavailable
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (studentId) {
        try {
          setStudent(await api.students.get(studentId))
          return
        } catch (e) {
          if (e.status !== 404) throw e
        }
      }
      // No saved student (or it was deleted): fall back to the first one.
      const first = await api.students.list({ limit: 1 })
      if (first.items.length) {
        setStudentId(first.items[0].id)
        setStudent(first.items[0])
      } else {
        setStudent(null)
      }
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }, [studentId, setStudentId])

  useEffect(() => {
    load()
  }, [load])

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
