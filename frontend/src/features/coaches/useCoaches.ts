import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useCoaches(params?: {
  name?: string
  club_id?: number
  page?: number
  page_size?: number
}) {
  return useQuery({
    queryKey: ['coaches', params],
    queryFn: () => api.coaches.list(params),
    placeholderData: (prev) => prev,
  })
}

export function useCoach(id: number) {
  return useQuery({
    queryKey: ['coach', id],
    queryFn: () => api.coaches.get(id),
    enabled: Number.isFinite(id),
  })
}
