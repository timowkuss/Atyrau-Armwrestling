import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { useCompetition, useCompetitionResults } from '@/features/competitions/useCompetitions'
import { api } from '@/lib/api'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { MedalBadge } from '@/components/ui/Medal'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })
}

export function CompetitionDetail() {
  const { id } = useParams<{ id: string }>()
  const competitionId = Number(id)

  const competition = useCompetition(competitionId)
  const results = useCompetitionResults(competitionId)
  const photos = useQuery({
    queryKey: ['competition', competitionId, 'photos'],
    queryFn: () => api.competitions.photos(competitionId),
    enabled: Number.isFinite(competitionId),
  })

  if (competition.isLoading) return <LoadingState label="Загрузка турнира" />
  if (competition.isError) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <ErrorState
          title="Турнир не найден"
          message={(competition.error as Error).message}
          onRetry={() => competition.refetch()}
        />
      </div>
    )
  }
  if (!competition.data) return null

  const c = competition.data
  const resultsByCategory = (results.data ?? []).reduce<Record<string, typeof results.data>>((acc, r) => {
    ;(acc[r.category_name] ??= []).push(r)
    return acc
  }, {})

  return (
    <div className="mx-auto max-w-4xl px-5 py-12">
      <Link to="/competitions" className="text-sm text-steel hover:text-brass">
        ← ко всем турнирам
      </Link>

      <div className="plate mt-4 rounded-[var(--radius-rivet)] p-6">
        <p className="text-eyebrow text-rust">{formatDate(c.date)}</p>
        <h1 className="mt-2 font-display text-2xl text-bone sm:text-3xl">{c.name}</h1>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-sm text-steel">
          {c.location_city_name && <span>{c.location_city_name}</span>}
          <span>{c.organizer ?? 'Федерация армрестлинга Атырау'}</span>
          <span>{c.participants_count} участников</span>
        </div>
        {c.description && <p className="mt-4 max-w-2xl text-sm text-steel">{c.description}</p>}
        {c.categories.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {c.categories.map((cat) => (
              <span
                key={cat.id}
                className="text-eyebrow rounded-[var(--radius-rivet)] border border-steel-dim px-2 py-1 text-steel"
              >
                {cat.name} · {cat.hand === 'left' ? 'левая' : 'правая'}
              </span>
            ))}
          </div>
        )}
      </div>

      {photos.data && photos.data.length > 0 && (
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {photos.data.map((p) => (
            <img key={p.id} src={p.url} alt={p.caption ?? ''} className="aspect-square rounded-[var(--radius-rivet)] object-cover" />
          ))}
        </div>
      )}

      <section className="mt-10 mb-16">
        <h2 className="font-display text-xl text-bone">Результаты</h2>
        <div className="rivet-line my-4" />
        {results.isLoading && <LoadingState label="Загрузка результатов" />}
        {results.isError && (
          <ErrorState message={(results.error as Error).message} onRetry={() => results.refetch()} />
        )}
        {results.data && results.data.length === 0 && (
          <EmptyState title="Результаты ещё не внесены" />
        )}
        {Object.entries(resultsByCategory).map(([category, rows]) => (
          <div key={category} className="mb-6">
            <h3 className="font-display text-sm text-brass">{category}</h3>
            <table className="mt-2 w-full border-collapse text-left text-sm">
              <tbody>
                {rows?.map((r, i) => (
                  <tr key={i} className="border-b border-steel-dim/15">
                    <td className="py-2 pr-4 font-mono text-bone">{r.place ?? '—'}</td>
                    <td className="py-2 pr-4">
                      <Link to={`/athletes/${r.athlete_id}`} className="text-bone hover:text-brass">
                        {r.athlete_name}
                      </Link>
                    </td>
                    <td className="py-2 pr-4 text-steel">{r.club_name ?? '—'}</td>
                    <td className="py-2">
                      <MedalBadge medal={r.medal} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </section>
    </div>
  )
}
