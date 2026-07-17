import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useAthleteRankings() {
  return useQuery({ queryKey: ['rankings', 'athletes'], queryFn: () => api.rankings.athletes() })
}

export function useClubRankings() {
  return useQuery({ queryKey: ['rankings', 'clubs'], queryFn: () => api.rankings.clubs() })
}
