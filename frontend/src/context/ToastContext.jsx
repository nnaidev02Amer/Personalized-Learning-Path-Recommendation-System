import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'

const ToastContext = createContext(null)
let nextId = 1

const STYLES = {
  success: { icon: CheckCircle2, cls: 'text-good' },
  error: { icon: AlertTriangle, cls: 'text-critical' },
  info: { icon: Info, cls: 'text-brand' },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const push = useCallback((toast) => {
    const id = nextId++
    setToasts((t) => [...t.slice(-3), { id, type: 'info', ...toast }])
    setTimeout(() => dismiss(id), toast.type === 'error' ? 7000 : 4000)
  }, [dismiss])

  const value = useMemo(() => ({
    push,
    success: (title, message) => push({ type: 'success', title, message }),
    error: (title, message) => push({ type: 'error', title, message }),
    info: (title, message) => push({ type: 'info', title, message }),
  }), [push])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-4 bottom-4 z-[60] flex flex-col items-end gap-2 sm:left-auto sm:w-96"
           role="region" aria-live="polite" aria-label="Notifications">
        {toasts.map(({ id, type, title, message }) => {
          const { icon: Icon, cls } = STYLES[type] || STYLES.info
          return (
            <div key={id} className="pointer-events-auto flex w-full items-start gap-3 rounded-xl border border-line bg-surface p-4 shadow-lg">
              <Icon className={`mt-0.5 size-5 shrink-0 ${cls}`} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">{title}</p>
                {message && <p className="mt-0.5 text-sm text-ink-2">{message}</p>}
              </div>
              <button onClick={() => dismiss(id)} className="rounded p-0.5 text-ink-3 hover:text-ink" aria-label="Dismiss">
                <X className="size-4" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
