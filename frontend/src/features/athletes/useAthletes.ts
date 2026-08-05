import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { AthleteListParams } from '@/types/api'

export function useAthletes(params: AthleteListParams) {
  return useQuery({
    queryKey: ['athletes', params],
    queryFn: () => api.athletes.list(params),
    placeholderData: (prev) => prev,
  })
}

export function useAthlete(id: number) {
  return useQuery({
    queryKey: ['athlete', id],
    queryFn: () => api.athletes.get(id),
    enabled: Number.isFinite(id),
  })
}

export function useAthleteBirthdays() {
  return useQuery({
    queryKey: ['athletes', 'birthdays'],
    queryFn: () => api.athletes.birthdays(),
    // Именинники обновляются не чаще раза в день — долгий staleTime
    // спасает главную от лишних запросов при переключении вкладок.
    staleTime: 1000 * 60 * 60 * 6,
  })
}

export function useAthleteHistory(id: number) {
  return useQuery({
    queryKey: ['athlete', id, 'history'],
    queryFn: () => api.athletes.history(id),
    enabled: Number.isFinite(id),
  })
}

export function useAthleteMatches(id: number) {
  return useQuery({
    queryKey: ['athlete', id, 'matches'],
    queryFn: () => api.athletes.matches(id),
    enabled: Number.isFinite(id),
  })
}
