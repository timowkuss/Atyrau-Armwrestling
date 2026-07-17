import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useCities() {
  return useQuery({
    queryKey: ['reference', 'cities'],
    queryFn: () => api.reference.cities(),
    staleTime: 5 * 60_000,
  })
}
