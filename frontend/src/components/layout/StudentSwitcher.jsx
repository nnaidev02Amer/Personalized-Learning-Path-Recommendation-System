import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Loader2, Search } from 'lucide-react'
import { api } from '../../api/client'
import { useStudent } from '../../context/StudentContext'
import { useApi, useDebounced } from '../../hooks/useApi'
import { initials } from '../../utils/format'

export function Avatar({ name, size = 'md' }) {
  const cls = size === 'lg' ? 'size-14 text-lg' : size === 'sm' ? 'size-7 text-xs' : 'size-9 text-sm'
  return (
    <span className={`grid shrink-0 place-items-center rounded-full bg-brand-soft font-semibold text-brand ${cls}`} aria-hidden>
      {initials(name)}
    </span>
  )
}

/** Choose which student's data the app shows (no authentication yet). */
export default function StudentSwitcher() {
  const { student, setStudentId } = useStudent()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const debounced = useDebounced(query)
  const box = useRef(null)
  const { data, loading, error } = useApi(
    open ? () => api.students.list({ search: debounced, limit: 15 }) : null, [open, debounced])

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => !box.current?.contains(e.target) && setOpen(false)
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  return (
    <div className="relative" ref={box}>
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}
              className="flex max-w-[15rem] items-center gap-2 rounded-xl border border-line bg-surface py-1.5 pl-1.5 pr-2.5 text-left hover:bg-surface-2">
        <Avatar name={student?.name || '?'} size="sm" />
        <span className="hidden min-w-0 sm:block">
          <span className="block truncate text-sm font-medium text-ink">{student?.name || 'Select student'}</span>
          <span className="block text-xs text-ink-3">Student #{student?.id ?? '—'}</span>
        </span>
        <ChevronDown className="size-4 shrink-0 text-ink-3" aria-hidden />
      </button>

      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-surface p-2 shadow-xl">
          <label className="flex items-center gap-2 rounded-lg border border-line px-2.5">
            <Search className="size-4 text-ink-3" aria-hidden />
            <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search students…"
                   className="h-9 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-3" aria-label="Search students" />
          </label>
          <p className="px-2 pt-2 text-xs text-ink-3">Viewing as — choose a student</p>
          <ul role="listbox" className="mt-1 max-h-72 overflow-y-auto">
            {loading && <li className="flex justify-center py-4"><Loader2 className="size-5 animate-spin text-ink-3" /></li>}
            {error && <li className="px-2 py-3 text-sm text-critical">{error.message}</li>}
            {!loading && data?.items.length === 0 && <li className="px-2 py-3 text-sm text-ink-3">No students match “{query}”.</li>}
            {!loading && data?.items.map((s) => (
              <li key={s.id}>
                <button role="option" aria-selected={s.id === student?.id}
                        onClick={() => { setStudentId(s.id); setOpen(false); setQuery('') }}
                        className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-surface-2">
                  <Avatar name={s.name} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-ink">{s.name}</span>
                    <span className="block truncate text-xs text-ink-3">#{s.id} · {s.learning_style || 'style not set'}</span>
                  </span>
                  {s.id === student?.id && <Check className="size-4 text-brand" aria-hidden />}
                </button>
              </li>
            ))}
          </ul>
          {data && data.total > data.items.length && (
            <p className="border-t border-line px-2 pt-2 text-xs text-ink-3">{data.total} students — type to search</p>
          )}
        </div>
      )}
    </div>
  )
}
