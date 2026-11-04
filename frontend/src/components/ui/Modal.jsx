import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

export default function Modal({ open, onClose, title, children, footer, size = 'md' }) {
  const panel = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const previous = document.activeElement
    panel.current?.focus()
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      previous?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null
  const width = size === 'lg' ? 'sm:max-w-3xl' : 'sm:max-w-lg'
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
           className={`relative flex max-h-[92vh] w-full flex-col rounded-t-2xl border border-line bg-surface shadow-2xl outline-none sm:rounded-2xl ${width}`}>
        <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Close">
            <X className="size-5" />
          </button>
        </header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-4">{footer}</footer>}
      </div>
    </div>,
    document.body,
  )
}
