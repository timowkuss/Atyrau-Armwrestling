import { useId, useState } from 'react'
import { useCities } from '@/features/useCities'
import { useResolveCity } from '@/features/admin/useResolveCity'

const inputClass =
  'rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none'

interface CityComboboxProps {
  /** Текст, с которым поле показывается изначально (например, текущий
   * город при редактировании). Не управляемое значение — компонент сам
   * ведёт свой текст, а наружу отдаёт уже разрешённый city_id. */
  initialText?: string
  placeholder?: string
  className?: string
  /** Навесить required на инпут (для форм, где город обязателен). */
  required?: boolean
  /** Вызывается с id найденного/созданного города, либо undefined, если
   * поле пустое (или не менялось — в режиме редактирования это значит
   * «оставить как есть», совпадает с прежним поведением select'а). */
  onChange: (cityId: number | undefined) => void
}

export function CityCombobox({ initialText = '', placeholder = 'Город/район', className, required, onChange }: CityComboboxProps) {
  const listId = useId()
  const cities = useCities()
  const resolveCity = useResolveCity()
  const [text, setText] = useState(initialText)

  function resolve(value: string) {
    const trimmed = value.trim()
    if (!trimmed) {
      onChange(undefined)
      return
    }
    const existing = cities.data?.find((c) => c.name.toLowerCase() === trimmed.toLowerCase())
    if (existing) {
      onChange(existing.id)
      return
    }
    resolveCity.mutate(trimmed, { onSuccess: (city) => onChange(city.id) })
  }

  return (
    <>
      <input
        list={listId}
        required={required}
        placeholder={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={(e) => resolve(e.target.value)}
        className={className ?? inputClass}
      />
      <datalist id={listId}>
        {cities.data?.map((c) => (
          <option key={c.id} value={c.name} />
        ))}
      </datalist>
    </>
  )
}
