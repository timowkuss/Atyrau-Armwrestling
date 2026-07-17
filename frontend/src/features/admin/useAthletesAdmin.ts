import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { adminApi } from '@/lib/adminApi'
import type { AthleteInput, AthleteStatisticsUpdateInput, AthleteUpdateInput } from '@/types/api'

export function useAdminAthletes(name?: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'athletes', name],
    queryFn: () => adminApi.athletes.list(token!, name),
    enabled: !!token,
    placeholderData: (prev) => prev,
  })
}

export function useAdminAthleteStatistics(athleteId: number | null) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'athletes', athleteId, 'statistics'],
    queryFn: () => adminApi.athletes.getStatistics(token!, athleteId!),
    enabled: !!token && athleteId !== null,
  })
}

export function useCreateAthlete() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AthleteInput) => adminApi.athletes.create(token!, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'athletes'] }),
  })
}

export function useUpdateAthlete() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AthleteUpdateInput }) =>
      adminApi.athletes.update(token!, id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'athletes'] }),
  })
}

export function useDeleteAthlete() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.athletes.remove(token!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'athletes'] }),
  })
}

export function useUpdateAthleteStatistics() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AthleteStatisticsUpdateInput }) =>
      adminApi.athletes.updateStatistics(token!, id, payload),
    onSuccess: (_data, vars) => qc.invalidateQueries({ queryKey: ['admin', 'athletes', vars.id, 'statistics'] }),
  })
}

export function useRecalculateAthleteStatistics() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.athletes.recalculateStatistics(token!, id),
    onSuccess: (_data, id) => qc.invalidateQueries({ queryKey: ['admin', 'athletes', id, 'statistics'] }),
  })
}
