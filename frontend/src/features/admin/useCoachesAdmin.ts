import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { api } from '@/lib/api'
import { adminApi } from '@/lib/adminApi'
import type { CoachInput } from '@/types/api'

export function useAdminCoachesList() {
  return useQuery({
    queryKey: ['admin', 'coaches', 'list-via-public'],
    queryFn: () => api.coaches.list({ page_size: 200 }),
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
