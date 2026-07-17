import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { adminApi } from '@/lib/adminApi'
import type { CompetitionAdminUpdateInput, GalleryDocumentInput } from '@/types/api'

export function useAdminCompetitions() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'competitions'],
    queryFn: () => adminApi.competitions.list(token!),
    enabled: !!token,
  })
}

export function useUpdateCompetition() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: CompetitionAdminUpdateInput }) =>
      adminApi.competitions.update(token!, id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'competitions'] }),
  })
}

export function useAdminDocuments(competitionId: number | null) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'competitions', competitionId, 'documents'],
    queryFn: () => adminApi.competitions.documents.list(token!, competitionId!),
    enabled: !!token && competitionId !== null,
  })
}

export function useCreateDocument() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ competitionId, payload }: { competitionId: number; payload: GalleryDocumentInput }) =>
      adminApi.competitions.documents.create(token!, competitionId, payload),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ['admin', 'competitions', vars.competitionId, 'documents'] }),
  })
}

export function useDeleteDocument() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ competitionId, documentId }: { competitionId: number; documentId: number }) =>
      adminApi.competitions.documents.remove(token!, competitionId, documentId),
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ['admin', 'competitions', vars.competitionId, 'documents'] }),
  })
}
