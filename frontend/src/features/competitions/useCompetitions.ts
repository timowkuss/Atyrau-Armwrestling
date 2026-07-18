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

export function useCompetitionBracket(id: number) {
  return useQuery({
    queryKey: ['competition', id, 'bracket'],
    queryFn: () => api.competitions.bracket(id),
    enabled: Number.isFinite(id),
  })
}

// Живая очередь по столам — во время турнира меняется каждую минуту,
// поэтому опрашиваем сервер, а не полагаемся на один запрос при заходе
// на страницу. Останавливаем опрос, если вкладка не активна.
export function useCompetitionQueue(id: number) {
  return useQuery({
    queryKey: ['competition', id, 'queue'],
    queryFn: () => api.competitions.queue(id),
    enabled: Number.isFinite(id),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
  })
}
