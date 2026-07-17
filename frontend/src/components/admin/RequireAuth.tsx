import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/features/auth/AuthContext'
import { LoadingState } from '@/components/ui/States'
import type { RoleCode } from '@/types/api'

export function RequireAuth({ children, roles }: { children: ReactNode; roles?: RoleCode[] }) {
  const { token, user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <LoadingState label="Проверка доступа" />

  if (!token || !user) {
    return <Navigate to="/admin/login" state={{ from: location }} replace />
  }

  if (roles && !roles.includes(user.role_code)) {
    return (
      <div className="mx-auto max-w-lg px-5 py-24 text-center">
        <p className="text-eyebrow text-danger">Доступ запрещён</p>
        <h1 className="mt-2 font-display text-2xl text-bone">Недостаточно прав</h1>
        <p className="mt-2 text-steel">
          Роль «{user.role_code}» не имеет доступа к этому разделу админки.
        </p>
      </div>
    )
  }

  return <>{children}</>
}
