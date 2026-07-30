import { Link } from 'react-router-dom'
import { useEloRankings } from '@/features/rankings/useRankings'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'

export function Rankings() {
  const elo = useEloRankings()

  return (
    <div className="mx-auto max-w-4xl px-5 py-12">
      <div className="text-center">
        <p className="font-mono text-xs font-medium uppercase tracking-[0.25em] text-rust/80">Итоговый зачёт</p>
        <h1 className="mt-3 font-display text-4xl font-bold leading-tight text-bone sm:text-5xl">
          Рейтинги
        </h1>
        <p className="mt-2 text-sm text-steel-dim">
          Топ спортсменов по рейтингу Rating
        </p>
      </div>

      <div className="mt-10">
        {elo.isLoading && <LoadingState label="Загрузка рейтинга" />}
        {elo.isError && <ErrorState message={(elo.error as Error).message} onRetry={() => elo.refetch()} />}
        {elo.data && elo.data.length === 0 && <EmptyState title="Рейтинг ещё не сформирован" />}
        {elo.data && elo.data.length > 0 && (
          <div className="space-y-3">
            {elo.data.map((r) => (
              <Link
                key={r.athlete_id}
                to={`/athletes/${r.athlete_id}`}
                className="group relative block overflow-hidden rounded-2xl border border-steel-dim/15 bg-gradient-to-br from-petrol/30 to-ink-soft/70 p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-brass/25 hover:shadow-[0_8px_30px_-6px_rgba(201,162,39,0.1)] sm:p-5"
              >
                <div className="pointer-events-none absolute -right-12 -top-12 h-28 w-28 rounded-full bg-brass/5 blur-3xl transition-all duration-500 group-hover:bg-brass/10" />
                <div className="flex items-center gap-4">
                  <div className={`relative flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl font-display text-sm font-bold transition-all duration-300 ${
                    r.position <= 3
                      ? r.position === 1
                        ? 'bg-gradient-to-br from-yellow-500/20 to-yellow-600/10 text-yellow-400 shadow-[0_0_12px_-2px_rgba(234,179,8,0.2)]'
                        : r.position === 2
                          ? 'bg-gradient-to-br from-slate-300/20 to-slate-400/10 text-slate-300 shadow-[0_0_12px_-2px_rgba(148,163,184,0.2)]'
                          : 'bg-gradient-to-br from-amber-700/20 to-amber-800/10 text-amber-600 shadow-[0_0_12px_-2px_rgba(180,83,9,0.2)]'
                      : 'bg-ink/60 text-steel-dim'
                  }`}>
                    {r.position}
                  </div>
                  <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl border border-steel-dim/15 bg-ink font-display text-xs text-steel-dim transition-all duration-300 group-hover:border-brass/30">
                    <span className="text-lg">{r.athlete_name.charAt(0)}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-display text-base font-semibold text-bone transition-colors group-hover:text-brass sm:text-lg">
                      {r.athlete_name}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 font-mono text-xs text-steel-dim">
                      {r.club_name && (
                        <span className="truncate">{r.club_name}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-rust/60">Rating</span>
                    <span className="font-display text-xl font-bold text-rust sm:text-2xl">{r.elo_combined}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
