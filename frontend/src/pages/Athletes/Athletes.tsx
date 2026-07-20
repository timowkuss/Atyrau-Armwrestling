import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAthletes } from '@/features/athletes/useAthletes'
import { AthleteCard } from '@/components/ui/AthleteCard'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { Pagination } from '@/components/ui/Pagination'

const PAGE_SIZE = 12

export function Athletes() {
  const [params, setParams] = useSearchParams()
  const [nameInput, setNameInput] = useState(params.get('name') ?? '')

  const page = Number(params.get('page') ?? '1')
  const name = params.get('name') ?? undefined
  const gender = (params.get('gender') as 'male' | 'female' | undefined) ?? undefined
  const rank = params.get('rank') ?? undefined

  const { data, isLoading, isError, error, refetch, isPlaceholderData } = useAthletes({
    name,
    gender,
    rank,
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

  function submitName(e: React.FormEvent) {
    e.preventDefault()
    updateParam('name', nameInput.trim() || null)
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-12">
      <p className="text-eyebrow text-rust">База спортсменов</p>
      <h1 className="mt-2 font-display text-3xl text-bone">Спортсмены</h1>
      <p className="mt-2 max-w-2xl text-steel">
        Единая база федерации: карточка появляется здесь сразу после регистрации спортсмена
        в судейском приложении на турнире.
      </p>

      {/* Фильтры */}
      <div className="plate mt-8 flex flex-col gap-4 rounded-[var(--radius-rivet)] p-4 sm:flex-row sm:flex-wrap sm:items-end">
        <form onSubmit={submitName} className="flex flex-1 flex-col gap-1 min-w-[200px]">
          <label htmlFor="athlete-name" className="text-eyebrow text-steel">
            Имя
          </label>
          <input
            id="athlete-name"
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            placeholder="Поиск по имени…"
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone placeholder:text-steel-dim focus:border-brass focus:outline-none"
          />
        </form>

        <div className="flex flex-col gap-1">
          <label htmlFor="athlete-gender" className="text-eyebrow text-steel">
            Пол
          </label>
          <select
            id="athlete-gender"
            value={gender ?? ''}
            onChange={(e) => updateParam('gender', e.target.value || null)}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          >
            <option value="">Все</option>
            <option value="male">Мужчины</option>
            <option value="female">Женщины</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="athlete-rank" className="text-eyebrow text-steel">
            Разряд
          </label>
          <input
            id="athlete-rank"
            defaultValue={rank ?? ''}
            onBlur={(e) => updateParam('rank', e.target.value.trim() || null)}
            placeholder="напр. КМС"
            className="w-32 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone placeholder:text-steel-dim focus:border-brass focus:outline-none"
          />
        </div>

        <button
          type="button"
          onClick={submitName}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone transition-colors hover:bg-rust-dim"
        >
          Применить
        </button>

        {(name || gender || rank) && (
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
        {isLoading && <LoadingState label="Загрузка спортсменов" />}
        {isError && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
        {data && data.items.length === 0 && (
          <EmptyState title="Никого не нашли" message="Попробуйте изменить фильтры поиска." />
        )}
        {data && data.items.length > 0 && (
          <div
            className="grid gap-5 transition-opacity sm:grid-cols-2 lg:grid-cols-3"
            style={{ opacity: isPlaceholderData ? 0.6 : 1 }}
          >
            {data.items.map((a) => (
              <AthleteCard key={a.id} athlete={a} />
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
