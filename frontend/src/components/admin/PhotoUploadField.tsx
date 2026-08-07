import { useRef, useState } from 'react'
import { useAuth } from '@/features/auth/useAuth'
import { adminApi } from '@/lib/adminApi'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'

interface PhotoUploadFieldProps {
  value: string | null | undefined
  onChange: (url: string) => void
  /** РџРѕРєР°Р·Р°С‚СЊ РїРѕРІРµСЂС… С‚РµРєСѓС‰РµРіРѕ Р·РЅР°С‡РµРЅРёСЏ (РІ С„РѕСЂРјРµ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ, РіРґРµ value
   * РёР· С„РѕСЂРјС‹ РµС‰С‘ РїСѓСЃС‚РѕР№, Р° РїСЂРµРІСЊСЋ РЅР°РґРѕ Р±СЂР°С‚СЊ РёР· СѓР¶Рµ СЃРѕС…СЂР°РЅС‘РЅРЅРѕР№ Р·Р°РїРёСЃРё). */
  fallbackPreview?: string | null
  size?: number
  /** 'circle' (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ, РєР°Рє РґР»СЏ СЃРїРѕСЂС‚СЃРјРµРЅРѕРІ) РёР»Рё 'square' вЂ” РјСЏРіРєРѕ
   * СЃРєСЂСѓРіР»С‘РЅРЅС‹Р№ РєРІР°РґСЂР°С‚, РєСЂСѓРїРЅРµРµ РїРѕРґС…РѕРґРёС‚ РґР»СЏ С‚СЂРµРЅРµСЂСЃРєРёС… РєР°СЂС‚РѕС‡РµРє. */
  shape?: 'circle' | 'square'
}

/** РљРЅРѕРїРєР° РІС‹Р±РѕСЂР°/СЃСЉС‘РјРєРё С„РѕС‚Рѕ + Р·Р°РіСЂСѓР·РєР° РЅР° Cloudinary С‡РµСЂРµР·
 * POST /admin/media/upload. РќР° С‚РµР»РµС„РѕРЅРµ РѕС‚РєСЂС‹РІР°РµС‚СЃСЏ СЃРёСЃС‚РµРјРЅС‹Р№ РІС‹Р±РѕСЂ:
 * СЃРЅСЏС‚СЊ РєР°РјРµСЂРѕР№ РёР»Рё РІС‹Р±СЂР°С‚СЊ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РµРµ С„РѕС‚Рѕ РёР· РіР°Р»РµСЂРµРё. */
export function PhotoUploadField({
  value,
  onChange,
  fallbackPreview,
  size = 56,
  shape = 'circle',
}: PhotoUploadFieldProps) {
  const { token } = useAuth()
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const preview = cloudinaryThumb(value || fallbackPreview, size)
  const roundedClass = shape === 'square' ? 'rounded-2xl' : 'rounded-full'

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // С‡С‚РѕР±С‹ РїРѕРІС‚РѕСЂРЅС‹Р№ РІС‹Р±РѕСЂ С‚РѕРіРѕ Р¶Рµ С„Р°Р№Р»Р° С‚РѕР¶Рµ СЃСЂР°Р±РѕС‚Р°Р»
    if (!file || !token) return
    setError(null)
    setUploading(true)
    try {
      const result = await adminApi.media.upload(token, file)
      onChange(result.url)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      {preview ? (
        <img
          src={preview}
          alt=""
          style={{ height: size, width: size }}
          className={`flex-shrink-0 ${roundedClass} object-cover border border-steel-dim`}
          onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
        />
      ) : (
        <div
          style={{ height: size, width: size }}
          className={`flex-shrink-0 ${roundedClass} bg-ink border border-steel-dim`}
        />
      )}
      <div className="flex flex-col gap-1">
        <button
          type="button"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
          className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass disabled:opacity-50"
        >
          {uploading ? 'Р—Р°РіСЂСѓР·РєР°вЂ¦' : 'рџ“· Р¤РѕС‚Рѕ'}
        </button>
        {error && <p className="text-xs text-danger">{error}</p>}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleFile}
        className="hidden"
      />
    </div>
  )
}
