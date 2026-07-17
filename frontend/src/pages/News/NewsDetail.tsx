import { Link, useParams } from 'react-router-dom'
import { useNewsDetail } from '@/features/news/useNews'
import { LoadingState, ErrorState } from '@/components/ui/States'

export function NewsDetail() {
  const { slug } = useParams<{ slug: string }>()
  const { data, isLoading, isError, error, refetch } = useNewsDetail(slug!)

  if (isLoading) return <LoadingState label="Загрузка новости" />
  if (isError || !data)
    return (
      <div className="mx-auto max-w-2xl px-5 py-16">
        <ErrorState title="Новость не найдена" message={(error as Error)?.message} onRetry={() => refetch()} />
      </div>
    )

  return (
    <div className="mx-auto max-w-2xl px-5 py-12">
      <Link to="/news" className="text-sm text-steel hover:text-brass">
        ← ко всем новостям
      </Link>
      {data.published_at && (
        <p className="text-eyebrow mt-4 text-rust">{new Date(data.published_at).toLocaleDateString('ru-RU')}</p>
      )}
      <h1 className="mt-2 font-display text-2xl text-bone sm:text-3xl">{data.title}</h1>
      {data.content && <p className="mt-6 whitespace-pre-wrap text-steel">{data.content}</p>}
    </div>
  )
}
