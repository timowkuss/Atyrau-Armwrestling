import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAthleteRankings, useClubRankings } from '@/features/rankings/useRankings'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'

export function Rankings() {
  const [tab, setTab] = useState<'athletes' | 'clubs'>('athletes')
  const athletes = useAthleteRankings()
  const clubs = useClubRankings()

  return (
    <div className="mx-auto max-w-3xl px-5 py-12">
      <p className="text-eyebrow text-rust">Итоговый зачёт</p>
      <h1 className="mt-2 font-display text-3xl text-bone">Рейтинги</h1>

      <div className="mt-6 flex gap-2">
        <button
          onClick={() => setTab('athletes')}
          className={`text-eyebrow rounded-[var(--radius-rivet)] px-3 py-1.5 ${tab === 'athletes' ? 'bg-petrol-2 text-brass' : 'border border-steel-dim text-steel'}`}
        >
          Спортсмены
        </button>
        <button
          onClick={() => setTab('clubs')}
          className={`text-eyebrow rounded-[var(--radius-rivet)] px-3 py-1.5 ${tab === 'clubs' ? 'bg-petrol-2 text-brass' : 'border border-steel-dim text-steel'}`}
        >
          Клубы
        </button>
      </div>

      <div className="mt-6">
        {tab === 'athletes' && (
          <>
            {athletes.isLoading && <LoadingState label="Загрузка рейтинга" />}
            {athletes.isError && <ErrorState message={(athletes.error as Error).message} onRetry={() => athletes.refetch()} />}
            {athletes.data && athletes.data.length === 0 && <EmptyState title="Рейтинг ещё не сформирован" />}
            {athletes.data && athletes.data.length > 0 && (
              <ol className="flex flex-col divide-y divide-steel-dim/15">
                {athletes.data.map((r, i) => (
                  <li key={r.athlete_id} className="flex items-center justify-between gap-3 py-2.5">
                    <span className="font-mono text-sm text-steel">{r.position ?? i + 1}</span>
                    <Link to={`/athletes/${r.athlete_id}`} className="flex-1 truncate text-bone hover:text-brass">
                      {r.athlete_name}
                    </Link>
                    <span className="font-mono text-xs text-steel-dim">{r.club_name ?? '—'}</span>
                    <span className="font-display text-brass">{r.points}</span>
                  </li>
                ))}
              </ol>
            )}
          </>
        )}
        {tab === 'clubs' && (
          <>
            {clubs.isLoading && <LoadingState label="Загрузка рейтинга" />}
            {clubs.isError && <ErrorState message={(clubs.error as Error).message} onRetry={() => clubs.refetch()} />}
            {clubs.data && clubs.data.length === 0 && <EmptyState title="Рейтинг ещё не сформирован" />}
            {clubs.data && clubs.data.length > 0 && (
              <ol className="flex flex-col divide-y divide-steel-dim/15">
                {clubs.data.map((r, i) => (
                  <li key={r.club_id} className="flex items-center justify-between gap-3 py-2.5">
                    <span className="font-mono text-sm text-steel">{r.position ?? i + 1}</span>
                    <span className="flex-1 truncate text-bone">{r.club_name}</span>
                    <span className="font-mono text-xs text-steel-dim">
                      {r.gold_count}·{r.silver_count}·{r.bronze_count}
                    </span>
                    <span className="font-display text-brass">{r.points}</span>
                  </li>
                ))}
              </ol>
            )}
          </>
        )}
      </div>
    </div>
  )
}
