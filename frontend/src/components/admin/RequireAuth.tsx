import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'
import { LoadingState } from '@/components/ui/States'
import type { RoleCode } from '@/types/api'

export function RequireAuth({ children, roles }: { children: ReactNode; roles?: RoleCode[] }) {
  const { token, user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <LoadingState label="РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїР°" />

  if (!token || !user) {
    return <Navigate to="/admin/login" state={{ from: location }} replace />
  }

  if (roles && !roles.includes(user.role_code)) {
    return (
      <div className="mx-auto max-w-lg px-5 py-24 text-center">
        <p className="text-eyebrow text-danger">Р”РѕСЃС‚СѓРї Р·Р°РїСЂРµС‰С‘РЅ</p>
        <h1 className="mt-2 font-display text-2xl text-bone">РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РїСЂР°РІ</h1>
        <p className="mt-2 text-steel">
          Р РѕР»СЊ В«{user.role_code}В» РЅРµ РёРјРµРµС‚ РґРѕСЃС‚СѓРїР° Рє СЌС‚РѕРјСѓ СЂР°Р·РґРµР»Сѓ Р°РґРјРёРЅРєРё.
        </p>
      </div>
    )
  }

  return <>{children}</>
}
