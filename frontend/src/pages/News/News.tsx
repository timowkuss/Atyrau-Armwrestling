import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useNewsList } from '@/features/news/useNews'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { Pagination } from '@/components/ui/Pagination'

export function News() {
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, error, refetch } = useNewsList(page)

  return (
    <div className="mx-auto max-w-4xl px-5 py-12">
      <p className="text-eyebrow text-rust">Федерация армрестлинга Атырау</p>
      <h1 className="mt-2 font-display text-3xl text-bone">Новости</h1>

      <div className="mt-8">
        {isLoading && <LoadingState label="Загрузка новостей" />}
        {isError && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
        {data && data.items.length === 0 && <EmptyState title="Новостей пока нет" />}
        {data && data.items.length > 0 && (
          <ul className="flex flex-col gap-4">
            {data.items.map((n) => (
              <li key={n.id}>
                <Link to={`/news/${n.slug}`} className="plate block rounded-[var(--radius-rivet)] p-5 hover:border-brass/50">
                  {n.published_at && (
                    <p className="text-eyebrow text-rust">{new Date(n.published_at).toLocaleDateString('ru-RU')}</p>
                  )}
                  <h2 className="mt-1 font-display text-lg text-bone">{n.title}</h2>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {data && <Pagination page={page} pageSize={12} total={data.total} onPageChange={setPage} />}
      </div>
    </div>
  )
}
