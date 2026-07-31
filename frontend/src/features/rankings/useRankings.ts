import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useAthleteRankings() {
  return useQuery({ queryKey: ['rankings', 'athletes'], queryFn: () => api.rankings.athletes() })
}

export function useClubRankings() {
  return useQuery({ queryKey: ['rankings', 'clubs'], queryFn: () => api.rankings.clubs() })
}

export function useCoachRankings(name?: string) {
  return useQuery({
    queryKey: ['rankings', 'coaches', name],
    queryFn: () => api.rankings.coaches({ name: name || undefined }),
  })
}

export function useEloRankings(params?: { gender?: string; hand?: string; name?: string }) {
  return useQuery({
    queryKey: ['rankings', 'elo', params],
    queryFn: () => api.rankings.elo(params),
  })
}
