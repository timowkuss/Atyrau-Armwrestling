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
    <div className="relative">
      {/* Hero-секция страницы */}
      <div className="relative overflow-hidden border-b border-steel-dim/15">
        <div className="pointer-events-none absolute inset-0 -z-10"
          style={{
            background: `
              radial-gradient(900px 400px at 75% 10%, rgba(201,162,39,0.08), transparent 60%),
              radial-gradient(700px 500px at 20% 90%, rgba(193,85,44,0.06), transparent 55%)
            `
          }}
        />
        <div className="mx-auto max-w-6xl px-5 py-6 sm:py-8">
          <p className="font-mono text-[10px] font-medium uppercase tracking-[0.25em] text-rust/80">База клубов</p>
          <h1 className="mt-2 font-display text-2xl font-bold leading-tight text-bone sm:text-3xl">
            Клубы
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-steel">
            Клубы армрестлинга Атырауской области — залы, спортсмены и тренеры.
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-5 py-6">
        {/* Фильтры */}
        <div className="relative overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/30 to-ink-soft/60 p-4">
          <div className="pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full bg-brass/5 blur-2xl" />
          <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
            <div className="flex w-full min-w-0 flex-1 flex-col gap-1.5 sm:min-w-[200px]">
              <label htmlFor="club-name" className="font-mono text-[11px] font-medium uppercase tracking-widest text-steel-dim">
                Название
              </label>
              <input
                id="club-name"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                placeholder="Поиск по названию…"
                autoComplete="off"
                className="w-full rounded-lg border border-steel-dim/20 bg-ink/80 px-3.5 py-2.5 text-sm text-bone placeholder:text-steel-dim/50 backdrop-blur transition-colors focus:border-brass/50 focus:bg-ink focus:outline-none"
              />
            </div>

            <div className="flex w-full min-w-0 flex-col gap-1.5 sm:w-auto sm:min-w-[180px]">
              <label htmlFor="club-city" className="font-mono text-[11px] font-medium uppercase tracking-widest text-steel-dim">
                Город / область
              </label>
              <select
                id="club-city"
                value={cityId ?? ''}
                onChange={(e) => updateParam('city', e.target.value || null)}
                className="w-full rounded-lg border border-steel-dim/20 bg-ink/80 px-3.5 py-2.5 text-sm text-bone backdrop-blur transition-colors focus:border-brass/50 focus:bg-ink focus:outline-none"
              >
                <option value="">Все города</option>
                {cities?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={() => updateParam('name', nameInput.trim() || null)}
              className="h-[42px] rounded-lg bg-rust px-5 text-sm font-semibold text-bone transition-all hover:bg-rust-dim hover:shadow-[0_4px_20px_-4px_rgba(193,85,44,0.4)]"
            >
              Найти
            </button>

            {hasFilters && (
              <button
                type="button"
                onClick={() => {
                  setNameInput('')
                  setParams(new URLSearchParams())
                }}
                className="h-[42px] text-sm text-steel-dim underline decoration-steel-dim/30 transition-colors hover:text-brass hover:decoration-brass/50"
              >
                Сбросить
              </button>
            )}
          </div>
        </div>

        <div className="mt-5">
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
              className="grid gap-5 transition-all duration-300 sm:grid-cols-2 2xl:grid-cols-3"
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
    </div>
  )
}
