import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/useAuth'
import { adminApi } from '@/lib/adminApi'
import type { CoachInput } from '@/types/api'

export function useAdminCoachesList() {
  // Р§РµСЂРµР· /admin/coaches (РЅРµ РїСѓР±Р»РёС‡РЅС‹Р№ /public/coaches) вЂ” С‚РѕР»СЊРєРѕ С‚Р°Рє
  // РѕС‚РґР°С‘С‚СЃСЏ РРРќ, РЅСѓР¶РЅС‹Р№ РґР»СЏ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ РєР°СЂС‚РѕС‡РєРё С‚СЂРµРЅРµСЂР° РІ Р°РґРјРёРЅРєРµ.
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'coaches', 'list'],
    queryFn: () => adminApi.coaches.list(token!),
    enabled: !!token,
    placeholderData: (prev) => prev,
  })
}

export function useCreateCoach() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CoachInput) => adminApi.coaches.create(token!, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'coaches'] }),
  })
}

export function useUpdateCoach() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<CoachInput> }) =>
      adminApi.coaches.update(token!, id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'coaches'] }),
  })
}

export function useDeleteCoach() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.coaches.remove(token!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'coaches'] }),
  })
}
