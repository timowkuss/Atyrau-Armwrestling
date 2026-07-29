import { useRef, useState } from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import { adminApi } from '@/lib/adminApi'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'

interface PhotoUploadFieldProps {
  value: string | null | undefined
  onChange: (url: string) => void
  /** Показать поверх текущего значения (в форме редактирования, где value
   * из формы ещё пустой, а превью надо брать из уже сохранённой записи). */
  fallbackPreview?: string | null
  size?: number
  /** 'circle' (по умолчанию, как для спортсменов) или 'square' — мягко
   * скруглённый квадрат, крупнее подходит для тренерских карточек. */
  shape?: 'circle' | 'square'
}

/** Кнопка выбора/съёмки фото + загрузка на Cloudinary через
 * POST /admin/media/upload. На телефоне открывается системный выбор:
 * снять камерой или выбрать существующее фото из галереи. */
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
    e.target.value = '' // чтобы повторный выбор того же файла тоже сработал
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
    <div className="flex items-center gap-3">
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
          {uploading ? 'Загрузка…' : '📷 Фото'}
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
