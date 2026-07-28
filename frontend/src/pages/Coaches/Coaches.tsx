import { useSearchParams } from 'react-router-dom'
import { useCoaches } from '@/features/coaches/useCoaches'
import { CoachCard } from '@/components/ui/CoachCard'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { Pagination } from '@/components/ui/Pagination'

const PAGE_SIZE = 12

export function Coaches() {
  const [params, setParams] = useSearchParams()
  const page = Number(params.get('page') ?? '1')

  const { data, isLoading, isError, error, refetch, isPlaceholderData } = useCoaches({
    page,
    page_size: PAGE_SIZE,
  })

  function updateParam(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next)
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-12">
      <p className="text-eyebrow text-rust">База федерации</p>
      <h1 className="mt-2 font-display text-3xl text-bone">Тренеры</h1>
      <p className="mt-2 max-w-2xl text-steel">
        Тренерский состав федерации Атырауской области — клубы, звания и подопечные спортсмены.
      </p>

      <div className="mt-8">
        {isLoading && <LoadingState label="Загрузка тренеров" />}
        {isError && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
        {data && data.items.length === 0 && (
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
