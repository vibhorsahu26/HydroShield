import { Bell, Shield, User } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const navItems = [
  { label: 'Dashboard', to: '/' },
  { label: 'Simulations', to: '/simulations' },
  { label: 'Scenarios', to: '/scenarios' },
  { label: 'Analysis', to: '/analysis' },
  { label: 'Exports', to: '/exports' },
]

function Header() {
  return (
    <header className="mx-auto mt-4 flex w-[calc(100%-2rem)] max-w-[1700px] items-center justify-between gap-4 rounded-t-[20px] border-2 border-sky-700/80 bg-sky-50/90 px-5 py-3 shadow-[0_4px_0_rgba(25,64,83,0.14)] backdrop-blur-sm">
      <div className="flex min-w-[220px] items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl border-2 border-sky-700/80 bg-gradient-to-b from-sky-100 to-cyan-200 shadow-inner">
          <Shield className="h-6 w-6 text-sky-700" />
        </div>
        <div className="text-3xl font-bold tracking-[-0.08em] text-sky-700">
          HydroShield
        </div>
      </div>

      <nav className="flex flex-1 flex-wrap items-center justify-center gap-2">
        {navItems.map(({ label, to }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `rounded-xl px-4 py-2 text-sm font-semibold transition ${
                isActive
                  ? 'border border-sky-700/60 bg-sky-200/60 text-sky-800 shadow-sm'
                  : 'text-slate-700 hover:bg-sky-100/60'
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="flex items-center gap-2">
        <button type="button" className="flex h-10 w-10 items-center justify-center rounded-full border-2 border-sky-700/80 bg-white/40 text-slate-700 transition hover:bg-sky-100" aria-label="Notifications">
          <Bell size={18} />
        </button>
        <button type="button" className="flex h-10 w-10 items-center justify-center rounded-full border-2 border-sky-700/80 bg-sky-100/80 text-slate-700 transition hover:bg-sky-200" aria-label="Profile">
          <User size={18} />
        </button>
      </div>
    </header>
  )
}

export default Header
