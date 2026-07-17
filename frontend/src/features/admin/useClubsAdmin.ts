import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { api } from '@/lib/api'
import { adminApi } from '@/lib/adminApi'
import type { ClubInput } from '@/types/api'

// Списка клубов в /admin нет (см. lib/adminApi.ts) — читаем максимально
// широкую страницу публичного списка, этого достаточно для админ-таблицы
// в масштабах одной областной федерации.
export function useAdminClubsList() {
  return useQuery({
    queryKey: ['admin', 'clubs', 'list-via-public'],
    queryFn: () => api.clubs.list({ page_size: 200 }),
  })
}

export function useCreateClub() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ClubInput) => adminApi.clubs.create(token!, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'clubs'] }),
  })
}

export function useUpdateClub() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<ClubInput> }) =>
      adminApi.clubs.update(token!, id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'clubs'] }),
  })
}

export function useDeleteClub() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.clubs.remove(token!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'clubs'] }),
  })
}
