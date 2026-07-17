import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { adminApi } from '@/lib/adminApi'
import type { NewsInput } from '@/types/api'

export function useAdminNewsList() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'news'],
    queryFn: () => adminApi.news.list(token!),
    enabled: !!token,
  })
}

export function useAdminNewsDetail(id: number | null) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'news', id],
    queryFn: () => adminApi.news.get(token!, id!),
    enabled: !!token && id !== null,
  })
}

export function useCreateNews() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: NewsInput) => adminApi.news.create(token!, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'news'] }),
  })
}

export function useUpdateNews() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<NewsInput> }) =>
      adminApi.news.update(token!, id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'news'] }),
  })
}

export function useDeleteNews() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.news.remove(token!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'news'] }),
  })
}
