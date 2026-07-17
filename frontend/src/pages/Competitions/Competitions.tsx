import { useSearchParams } from 'react-router-dom'
import { useCompetitions } from '@/features/competitions/useCompetitions'
import { CompetitionCard } from '@/components/ui/CompetitionCard'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { Pagination } from '@/components/ui/Pagination'

const PAGE_SIZE = 9
const CURRENT_YEAR = new Date().getFullYear()
const YEARS = Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - i)

export function Competitions() {
  const [params, setParams] = useSearchParams()
  const page = Number(params.get('page') ?? '1')
  const year = params.get('year') ? Number(params.get('year')) : undefined

  const { data, isLoading, isError, error, refetch, isPlaceholderData } = useCompetitions({
    status: 'published',
    year,
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

  return (
    <div className="mx-auto max-w-6xl px-5 py-12">
      <p className="text-eyebrow text-rust">Календарь федерации</p>
      <h1 className="mt-2 font-display text-3xl text-bone">Соревнования</h1>
      <p className="mt-2 max-w-2xl text-steel">
        Публикуются сразу после того, как организатор нажимает «Опубликовать результаты» в
        судейском приложении на площадке.
      </p>

      <div className="mt-8 flex flex-wrap items-center gap-2">
        <button
          onClick={() => updateParam('year', null)}
          className={`text-eyebrow rounded-[var(--radius-rivet)] px-3 py-1.5 transition-colors ${
            !year ? 'bg-petrol-2 text-brass' : 'border border-steel-dim text-steel hover:text-bone'
          }`}
        >
          Все годы
        </button>
        {YEARS.map((y) => (
          <button
            key={y}
            onClick={() => updateParam('year', String(y))}
            className={`text-eyebrow rounded-[var(--radius-rivet)] px-3 py-1.5 transition-colors ${
              year === y ? 'bg-petrol-2 text-brass' : 'border border-steel-dim text-steel hover:text-bone'
            }`}
          >
            {y}
          </button>
        ))}
      </div>

      <div className="mt-8">
        {isLoading && <LoadingState label="Загрузка турниров" />}
        {isError && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
        {data && data.items.length === 0 && (
          <EmptyState title="Турниров не найдено" message="Попробуйте выбрать другой год." />
        )}
        {data && data.items.length > 0 && (
          <div
            className="grid gap-4 transition-opacity sm:grid-cols-2 lg:grid-cols-3"
            style={{ opacity: isPlaceholderData ? 0.6 : 1 }}
          >
            {data.items.map((c) => (
              <CompetitionCard key={c.id} competition={c} />
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
