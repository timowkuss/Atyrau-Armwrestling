import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useClubs(params?: {
  name?: string
  city_id?: number
  page?: number
  page_size?: number
}) {
  return useQuery({
    queryKey: ['clubs', params],
    queryFn: () => api.clubs.list(params),
    placeholderData: (prev) => prev,
  })
}

export function useClub(id: number) {
  return useQuery({
    queryKey: ['club', id],
    queryFn: () => api.clubs.get(id),
    enabled: Number.isFinite(id),
  })
}
