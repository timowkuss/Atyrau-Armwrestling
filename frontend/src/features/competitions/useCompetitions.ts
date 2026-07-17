import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CompetitionListParams } from '@/types/api'

export function useCompetitions(params: CompetitionListParams) {
  return useQuery({
    queryKey: ['competitions', params],
    queryFn: () => api.competitions.list(params),
    placeholderData: (prev) => prev,
  })
}

export function useCompetition(id: number) {
  return useQuery({
    queryKey: ['competition', id],
    queryFn: () => api.competitions.get(id),
    enabled: Number.isFinite(id),
  })
}

export function useCompetitionResults(id: number) {
  return useQuery({
    queryKey: ['competition', id, 'results'],
    queryFn: () => api.competitions.results(id),
    enabled: Number.isFinite(id),
  })
}
