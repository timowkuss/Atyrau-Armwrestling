import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { adminApi } from '@/lib/adminApi'
import type { ClubInput } from '@/types/api'

export function useAdminClubsList() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'clubs', 'list'],
    queryFn: () => adminApi.clubs.list(token!),
    enabled: !!token,
  })
}

export function useAdminClubDetail(id: number | null) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'clubs', id, 'detail'],
    queryFn: () => adminApi.clubs.get(token!, id!),
    enabled: !!token && id !== null,
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

export function useAddClubMembers() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { athlete_ids: number[]; coach_ids: number[] } }) =>
      adminApi.clubs.addMembers(token!, id, payload),
    onSuccess: (_data, vars) => qc.invalidateQueries({ queryKey: ['admin', 'clubs', vars.id] }),
  })
}

export function useRemoveClubMembers() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { athlete_ids: number[]; coach_ids: number[] } }) =>
      adminApi.clubs.removeMembers(token!, id, payload),
    onSuccess: (_data, vars) => qc.invalidateQueries({ queryKey: ['admin', 'clubs', vars.id] }),
  })
}
