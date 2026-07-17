import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/features/auth/AuthContext'
import type { RoleCode } from '@/types/api'

interface NavItem {
  to: string
  label: string
  roles?: RoleCode[]
  end?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { to: '/admin', label: 'Обзор', end: true },
  { to: '/admin/clubs', label: 'Клубы', roles: ['super_admin', 'admin'] },
  { to: '/admin/coaches', label: 'Тренеры', roles: ['super_admin', 'admin'] },
  { to: '/admin/athletes', label: 'Спортсмены', roles: ['super_admin', 'admin'] },
  { to: '/admin/news', label: 'Новости', roles: ['super_admin', 'admin', 'editor'] },
  { to: '/admin/gallery', label: 'Медиа', roles: ['super_admin', 'admin', 'editor'] },
  { to: '/admin/competitions', label: 'Турниры (инфо)', roles: ['super_admin', 'admin'] },
]

export function AdminLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="flex min-h-screen bg-ink text-bone">
      <aside className="flex w-60 flex-shrink-0 flex-col border-r border-steel-dim/30 bg-ink-soft">
        <div className="flex items-center gap-3 px-5 py-5">
          <img src="/brand/logo-armsport.png" alt="Логотип федерации" className="h-9 w-auto" />
          <div>
            <p className="font-display text-sm font-bold uppercase tracking-wide text-bone">
              Atyrau<span className="text-rust"> Armsport</span>
            </p>
            <p className="text-eyebrow mt-0.5 text-steel">панель управления</p>
          </div>
        </div>
        <div className="rivet-line" />
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV_ITEMS.filter((item) => !item.roles || (user && item.roles.includes(user.role_code))).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-[var(--radius-rivet)] px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? 'bg-petrol-2 text-brass' : 'text-steel hover:bg-petrol/40 hover:text-bone'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="rivet-line" />
        <div className="p-4">
          <p className="truncate text-sm text-bone">{user?.full_name}</p>
          <p className="text-eyebrow text-brass">{user?.role_code}</p>
          <button
            onClick={logout}
            className="mt-3 w-full rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-2 text-sm text-steel transition-colors hover:border-danger hover:text-danger"
          >
            Выйти
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden">
        <div className="mx-auto max-w-4xl px-6 py-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
