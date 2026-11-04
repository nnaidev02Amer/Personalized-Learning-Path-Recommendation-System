import { NavLink } from 'react-router-dom'
import { GraduationCap, X } from 'lucide-react'
import { NAV_ITEMS } from './navigation'

function NavItems({ onNavigate }) {
  return (
    <nav className="flex flex-col gap-1" aria-label="Main">
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={onNavigate}
                 className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors
                   ${isActive ? 'bg-brand-soft text-brand' : 'text-ink-2 hover:bg-surface-2 hover:text-ink'}`}>
          <Icon className="size-[18px] shrink-0" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <span className="grid size-9 place-items-center rounded-xl bg-brand text-white">
        <GraduationCap className="size-5" aria-hidden />
      </span>
      <div>
        <p className="text-sm font-semibold leading-tight text-ink">PathWise</p>
        <p className="text-xs leading-tight text-ink-3">Personalized learning</p>
      </div>
    </div>
  )
}

export default function Sidebar({ mobileOpen, onClose }) {
  return (
    <>
      {/* Desktop */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-line bg-surface px-4 py-5 lg:flex">
        <Brand />
        <div className="mt-8 flex-1 overflow-y-auto"><NavItems /></div>
        <p className="px-2 text-xs text-ink-3">v2.0 · data from your local API</p>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-surface px-4 py-5 shadow-xl">
            <div className="flex items-center justify-between">
              <Brand />
              <button onClick={onClose} className="rounded-lg p-1.5 text-ink-3 hover:bg-surface-2" aria-label="Close menu">
                <X className="size-5" />
              </button>
            </div>
            <div className="mt-8 flex-1 overflow-y-auto"><NavItems onNavigate={onClose} /></div>
          </aside>
        </div>
      )}
    </>
  )
}
