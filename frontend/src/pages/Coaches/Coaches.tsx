import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useCoaches } from '@/features/coaches/useCoaches'
import { CoachCard } from '@/components/ui/CoachCard'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { Pagination } from '@/components/ui/Pagination'

const PAGE_SIZE = 12
const SEARCH_DEBOUNCE_MS = 350

export function Coaches() {
  const [params, setParams] = useSearchParams()
  const [nameInput, setNameInput] = useState(params.get('name') ?? '')

  const page = Number(params.get('page') ?? '1')
  const name = params.get('name') ?? undefined

  const { data, isLoading, isError, error, refetch, isPlaceholderData } = useCoaches({
    name,
    page,
    page_size: PAGE_SIZE,
  })

  function updateParam(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setParams(next)
  }

  // Живой поиск: применяем введённое имя в URL с небольшой задержкой после
  // того, как пользователь перестал печатать, без кнопки "Применить".
  useEffect(() => {
    const trimmed = nameInput.trim()
    if (trimmed === (name ?? '')) return
    const timer = setTimeout(() => {
      updateParam('name', trimmed || null)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nameInput])

  return (
    <div className="mx-auto max-w-6xl px-5 py-12">
      <p className="text-eyebrow text-rust">База федерации</p>
      <h1 className="mt-2 font-display text-3xl text-bone">Тренеры</h1>
      <p className="mt-2 max-w-2xl text-steel">
        Тренерский состав федерации Атырауской области — клубы, звания и подопечные спортсмены.
      </p>

      <div className="plate mt-8 flex flex-col gap-4 rounded-[var(--radius-rivet)] p-4 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="flex flex-1 flex-col gap-1 min-w-[200px]">
          <label htmlFor="coach-name" className="text-eyebrow text-steel">
            Имя
          </label>
          <input
            id="coach-name"
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            placeholder="Поиск по имени…"
            autoComplete="off"
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone placeholder:text-steel-dim focus:border-brass focus:outline-none"
          />
        </div>

        {nameInput && (
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
        {isLoading && <LoadingState label="Загрузка тренеров" />}
        {isError && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
        {data && data.items.length === 0 && name && (
          <EmptyState title="Никого не нашли" message="Попробуйте изменить запрос поиска." />
        )}
        {data && data.items.length === 0 && !name && (
          <EmptyState title="Пока никого нет" message="Тренеры появятся здесь после регистрации в федерации." />
        )}
        {data && data.items.length > 0 && (
          <div
            className="grid gap-5 transition-opacity sm:grid-cols-2 lg:grid-cols-3"
            style={{ opacity: isPlaceholderData ? 0.6 : 1 }}
          >
            {data.items.map((c) => (
              <CoachCard key={c.id} coach={c} />
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
