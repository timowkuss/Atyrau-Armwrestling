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

  function applyFilters() {
    updateParam('name', nameInput.trim() || null)
  }

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
          <p className="font-mono text-[10px] font-medium uppercase tracking-[0.25em] text-rust/80">База спортсменов</p>
          <h1 className="mt-2 font-display text-2xl font-bold leading-tight text-bone sm:text-3xl">
            Спортсмены
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-steel">
            Единая база федерации: карточка появляется здесь сразу после регистрации спортсмена
            в судейском приложении на турнире.
          </p>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-5 py-6">
        {/* Фильтры */}
        <div className="relative overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/30 to-ink-soft/60 p-4">
          <div className="pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full bg-brass/5 blur-2xl" />
          <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
            <form onSubmit={submitName} className="flex flex-1 flex-col gap-1.5 min-w-[200px]">
              <label htmlFor="athlete-name" className="font-mono text-[11px] font-medium uppercase tracking-widest text-steel-dim">
                Имя
              </label>
              <input
                id="athlete-name"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                placeholder="Поиск по имени…"
                className="rounded-lg border border-steel-dim/20 bg-ink/80 px-3.5 py-2.5 text-sm text-bone placeholder:text-steel-dim/50 backdrop-blur transition-colors focus:border-brass/50 focus:bg-ink focus:outline-none"
              />
            </form>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="athlete-gender" className="font-mono text-[11px] font-medium uppercase tracking-widest text-steel-dim">
                Пол
              </label>
              <select
                id="athlete-gender"
                value={gender ?? ''}
                onChange={(e) => updateParam('gender', e.target.value || null)}
                className="rounded-lg border border-steel-dim/20 bg-ink/80 px-3.5 py-2.5 text-sm text-bone backdrop-blur transition-colors focus:border-brass/50 focus:bg-ink focus:outline-none"
              >
                <option value="">Все</option>
                <option value="male">Мужчины</option>
                <option value="female">Женщины</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="athlete-rank" className="font-mono text-[11px] font-medium uppercase tracking-widest text-steel-dim">
                Разряд
              </label>
              <select
                id="athlete-rank"
                value={rank ?? ''}
                onChange={(e) => updateParam('rank', e.target.value || null)}
                className="rounded-lg border border-steel-dim/20 bg-ink/80 px-3.5 py-2.5 text-sm text-bone backdrop-blur transition-colors focus:border-brass/50 focus:bg-ink focus:outline-none"
              >
                <option value="">Все</option>
                <option value="КМС">КМС</option>
                <option value="МС">МС</option>
                <option value="МСМК">МСМК</option>
                <option value="ЗМС">ЗМС</option>
              </select>
            </div>

            <button
              type="button"
              onClick={applyFilters}
              className="h-[42px] rounded-lg bg-rust px-5 text-sm font-semibold text-bone transition-all hover:bg-rust-dim hover:shadow-[0_4px_20px_-4px_rgba(193,85,44,0.4)]"
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
                className="h-[42px] text-sm text-steel-dim underline decoration-steel-dim/30 transition-colors hover:text-brass hover:decoration-brass/50"
              >
                Сбросить
              </button>
            )}
          </div>
        </div>

        {/* Сетка */}
        <div className="mt-5">
          {isLoading && <LoadingState label="Загрузка спортсменов" />}
          {isError && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
          {data && data.items.length === 0 && (
            <EmptyState title="Никого не нашли" message="Попробуйте изменить фильтры поиска." />
          )}
          {data && data.items.length > 0 && (
            <div
              className="grid gap-5 transition-all duration-300 sm:grid-cols-2 lg:grid-cols-3"
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
    </div>
  )
}
