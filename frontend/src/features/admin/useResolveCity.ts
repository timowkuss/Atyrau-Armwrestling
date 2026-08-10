import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/useAuth'
import { adminApi } from '@/lib/adminApi'

/** Находит город по названию или создаёт новый — используется полем
 * свободного ввода города (CityCombobox), чтобы не ограничивать
 * пользователя предзаполненным справочником. */
export function useResolveCity() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => adminApi.reference.resolveCity(token!, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reference', 'cities'] }),
  })
}
