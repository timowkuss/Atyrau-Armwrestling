import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { adminApi } from '@/lib/adminApi'
import type { CoachInput } from '@/types/api'

export function useAdminCoachesList() {
  // Через /admin/coaches (не публичный /public/coaches) — только так
  // отдаётся ИИН, нужный для редактирования карточки тренера в админке.
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'coaches', 'list'],
    queryFn: () => adminApi.coaches.list(token!),
    enabled: !!token,
    placeholderData: (prev) => prev,
  })
}

export function useCreateCoach() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CoachInput) => adminApi.coaches.create(token!, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'coaches'] }),
  })
}

export function useUpdateCoach() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<CoachInput> }) =>
      adminApi.coaches.update(token!, id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'coaches'] }),
  })
}

export function useDeleteCoach() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.coaches.remove(token!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'coaches'] }),
  })
}
