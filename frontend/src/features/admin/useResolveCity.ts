import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/useAuth'
import { adminApi } from '@/lib/adminApi'

/** РќР°С…РѕРґРёС‚ РіРѕСЂРѕРґ РїРѕ РЅР°Р·РІР°РЅРёСЋ РёР»Рё СЃРѕР·РґР°С‘С‚ РЅРѕРІС‹Р№ вЂ” РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РїРѕР»РµРј
 * СЃРІРѕР±РѕРґРЅРѕРіРѕ РІРІРѕРґР° РіРѕСЂРѕРґР° (CityCombobox), С‡С‚РѕР±С‹ РЅРµ РѕРіСЂР°РЅРёС‡РёРІР°С‚СЊ
 * РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РїСЂРµРґР·Р°РїРѕР»РЅРµРЅРЅС‹Рј СЃРїСЂР°РІРѕС‡РЅРёРєРѕРј. */
export function useResolveCity() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => adminApi.reference.resolveCity(token!, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reference', 'cities'] }),
  })
}
