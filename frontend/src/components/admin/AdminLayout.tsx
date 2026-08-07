import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'
import type { RoleCode } from '@/types/api'

interface NavItem {
  to: string
  label: string
  roles?: RoleCode[]
  end?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { to: '/admin', label: 'РћР±Р·РѕСЂ', end: true },
  { to: '/admin/clubs', label: 'РљР»СѓР±С‹', roles: ['super_admin', 'admin'] },
  { to: '/admin/coaches', label: 'РўСЂРµРЅРµСЂС‹', roles: ['super_admin', 'admin'] },
  { to: '/admin/athletes', label: 'РЎРїРѕСЂС‚СЃРјРµРЅС‹', roles: ['super_admin', 'admin'] },
  { to: '/admin/news', label: 'РќРѕРІРѕСЃС‚Рё', roles: ['super_admin', 'admin', 'editor'] },
  { to: '/admin/gallery', label: 'РњРµРґРёР°', roles: ['super_admin', 'admin', 'editor'] },
  { to: '/admin/competitions', label: 'РўСѓСЂРЅРёСЂС‹ (РёРЅС„Рѕ)', roles: ['super_admin', 'admin'] },
]

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()

  return (
    <>
      <div className="flex items-center gap-3 px-5 py-5">
        <img src="/brand/logo-armsport.png" alt="Р›РѕРіРѕС‚РёРї С„РµРґРµСЂР°С†РёРё" className="h-9 w-auto" />
        <div>
          <p className="font-display text-sm font-bold uppercase tracking-wide text-bone">
            Atyrau<span className="text-rust"> Armsport</span>
          </p>
          <p className="text-eyebrow mt-0.5 text-steel">РїР°РЅРµР»СЊ СѓРїСЂР°РІР»РµРЅРёСЏ</p>
        </div>
      </div>
      <div className="rivet-line" />
      <nav className="flex flex-1 flex-col gap-1 p-3">
        {NAV_ITEMS.filter((item) => !item.roles || (user && item.roles.includes(user.role_code))).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
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
          Р’С‹Р№С‚Рё
        </button>
      </div>
    </>
  )
}

export function AdminLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [drawerOpen])

  return (
    <div className="flex min-h-screen bg-ink text-bone">
        {/* РЎР°Р№РґР±Р°СЂ вЂ” РїРѕСЃС‚РѕСЏРЅРЅРѕ РІРёРґРµРЅ РѕС‚ md Рё РІС‹С€Рµ */}
        <aside className="hidden w-60 flex-shrink-0 flex-col overflow-y-auto border-r border-steel-dim/30 bg-ink-soft md:flex">
          <SidebarContent />
        </aside>

      {/* РњРѕР±РёР»СЊРЅС‹Р№ off-canvas drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[80%] flex-col overflow-y-auto border-r border-steel-dim/30 bg-ink-soft">
            <SidebarContent onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* РњРѕР±РёР»СЊРЅР°СЏ РІРµСЂС…РЅСЏСЏ РїР°РЅРµР»СЊ СЃ РєРЅРѕРїРєРѕР№ РѕС‚РєСЂС‹С‚РёСЏ РјРµРЅСЋ */}
        <div className="flex min-w-0 items-center gap-3 border-b border-steel-dim/30 bg-ink-soft px-4 py-3 md:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[var(--radius-rivet)] text-bone"
            aria-label="РћС‚РєСЂС‹С‚СЊ РјРµРЅСЋ"
            aria-expanded={drawerOpen}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M4 6.5H20M4 12H20M4 17.5H20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
          <img src="/brand/logo-armsport.png" alt="Р›РѕРіРѕС‚РёРї С„РµРґРµСЂР°С†РёРё" className="h-8 w-auto flex-shrink-0" />
          <p className="truncate font-display text-sm font-bold uppercase tracking-wide text-bone">
            Atyrau<span className="text-rust"> Admin</span>
          </p>
        </div>

        <main className="flex-1 overflow-x-hidden">
          <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-10">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
