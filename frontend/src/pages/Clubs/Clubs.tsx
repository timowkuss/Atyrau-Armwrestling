import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useClubs } from '@/features/clubs/useClubs'
import { useCities } from '@/features/useCities'
import { ClubCard } from '@/components/ui/ClubCard'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { Pagination } from '@/components/ui/Pagination'

const PAGE_SIZE = 12
const SEARCH_DEBOUNCE_MS = 350

export function Clubs() {
  const [params, setParams] = useSearchParams()
  const [nameInput, setNameInput] = useState(params.get('name') ?? '')

  const page = Number(params.get('page') ?? '1')
  const name = params.get('name') ?? undefined
  const cityId = params.get('city') ? Number(params.get('city')) : undefined

  const { data, isLoading, isError, error, refetch, isPlaceholderData } = useClubs({
    name,
    city_id: cityId,
    page,
    page_size: PAGE_SIZE,
  })
  const { data: cities } = useCities()

  function updateParam(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setParams(next)
  }

  useEffect(() => {
    const trimmed = nameInput.trim()
    if (trimmed === (name ?? '')) return
    const timer = setTimeout(() => {
      updateParam('name', trimmed || null)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nameInput])

  const hasFilters = Boolean(name || cityId)

  return (
    <div className="mx-auto max-w-6xl px-5 py-12">
      <p className="text-eyebrow text-rust">База федерации</p>
      <h1 className="mt-2 font-display text-3xl text-bone">Клубы</h1>
      <p className="mt-2 max-w-2xl text-steel">
        Клубы армрестлинга Атырауской области — залы, спортсмены и тренеры.
      </p>

      <div className="plate mt-8 flex flex-col gap-4 rounded-[var(--radius-rivet)] p-4 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="flex min-w-[200px] flex-1 flex-col gap-1">
          <label htmlFor="club-name" className="text-eyebrow text-steel">
            Название
          </label>
          <input
            id="club-name"
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            placeholder="Поиск по названию…"
            autoComplete="off"
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone placeholder:text-steel-dim focus:border-brass focus:outline-none"
          />
        </div>

        <div className="flex min-w-[180px] flex-col gap-1">
          <label htmlFor="club-city" className="text-eyebrow text-steel">
            Город / область
          </label>
          <select
            id="club-city"
            value={cityId ?? ''}
            onChange={(e) => updateParam('city', e.target.value || null)}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          >
            <option value="">Все города</option>
            {cities?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {hasFilters && (
          <button
            type="button"
            onClick={() => {
              setNameInput('')
              setParams(new URLSearchParams())
            }}
            className="text-sm text-steel underline decoration-steel-dim hover:text-brass"
          >
            Сбросить
          </button>
        )}
      </div>

      <div className="mt-8">
        {isLoading && <LoadingState label="Загрузка клубов" />}
        {isError && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
        {data && data.items.length === 0 && hasFilters && (
          <EmptyState title="Ничего не нашли" message="Попробуйте изменить запрос поиска." />
        )}
        {data && data.items.length === 0 && !hasFilters && (
          <EmptyState title="Пока нет клубов" message="Клубы появятся здесь после регистрации в федерации." />
        )}
        {data && data.items.length > 0 && (
          <div
            className="grid gap-5 transition-opacity sm:grid-cols-2 lg:grid-cols-3"
            style={{ opacity: isPlaceholderData ? 0.6 : 1 }}
          >
            {data.items.map((c) => (
              <ClubCard key={c.id} club={c} />
            ))}
          </div>
        )}
        {data && (
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={data.total}
            onPageChange={(p) => updateParam('page', String(p))}
          />
        )}
      </div>
    </div>
  )
}
