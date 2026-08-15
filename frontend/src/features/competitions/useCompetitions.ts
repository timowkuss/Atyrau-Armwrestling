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

// Опрашиваем статус турнира, а не только сетку/очередь — иначе после
// «Завершить турнир» / «Возобновить турнир» в десктопе зритель видит
// старое состояние страницы, пока не обновит вкладку руками.
export function useCompetition(id: number) {
  return useQuery({
    queryKey: ['competition', id],
    queryFn: () => api.competitions.get(id),
    enabled: Number.isFinite(id),
    // Останавливаем опрос при ошибке (404/500): не долбим сервер раз в 15с
    // на странице «Турнир не найден».
    refetchInterval: (query) => (query.state.status === 'error' ? false : 15000),
    refetchIntervalInBackground: false,
  })
}

export function useCompetitionResults(id: number) {
  return useQuery({
    queryKey: ['competition', id, 'results'],
    queryFn: () => api.competitions.results(id),
    enabled: Number.isFinite(id),
  })
}

export function useCompetitionHandResults(id: number) {
  return useQuery({
    queryKey: ['competition', id, 'hand-results'],
    queryFn: () => api.competitions.handResults(id),
    enabled: Number.isFinite(id),
  })
}

export function useCompetitionParticipants(id: number) {
  return useQuery({
    queryKey: ['competition', id, 'participants'],
    queryFn: () => api.competitions.participants(id),
    enabled: Number.isFinite(id),
  })
}

// Сетка турнира: во время турнира пары/победители меняются по ходу
// раундов, поэтому опрашиваем сервер так же, как и живую очередь по
// столам — иначе зритель видит статичный снимок на момент открытия
// страницы, пока не обновит вкладку руками.
export function useCompetitionBracket(id: number) {
  return useQuery({
    queryKey: ['competition', id, 'bracket'],
    queryFn: () => api.competitions.bracket(id),
    enabled: Number.isFinite(id),
    refetchInterval: (query) => (query.state.status === 'error' ? false : 10000),
    refetchIntervalInBackground: false,
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
    refetchInterval: (query) => (query.state.status === 'error' ? false : 3000),
    refetchIntervalInBackground: false,
  })
}
