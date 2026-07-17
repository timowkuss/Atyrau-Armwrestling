import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useNewsList(page: number) {
  return useQuery({ queryKey: ['news', page], queryFn: () => api.news.list({ page, page_size: 12 }), placeholderData: (p) => p })
}

export function useNewsDetail(slug: string) {
  return useQuery({ queryKey: ['news', slug], queryFn: () => api.news.get(slug) })
}
