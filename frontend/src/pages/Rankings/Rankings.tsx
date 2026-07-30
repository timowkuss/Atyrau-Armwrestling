import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useEloRankings, useClubRankings, useCoachRankings } from '@/features/rankings/useRankings'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'

type Tab = 'athletes' | 'coaches' | 'clubs'

const handOptions = [
  { value: '', label: 'Общая' },
  { value: 'left', label: 'Левая' },
  { value: 'right', label: 'Правая' },
] as const

export function Rankings() {
  const [tab, setTab] = useState<Tab>('athletes')
  const [name, setName] = useState('')
  const [hand, setHand] = useState('')

  const elo = useEloRankings({ name: name || undefined, hand: hand || undefined })
  const clubs = useClubRankings()
  const coaches = useCoachRankings()

  const tabs: { key: Tab; label: string }[] = [
    { key: 'athletes', label: 'Спортсмены' },
    { key: 'coaches', label: 'Тренеры' },
    { key: 'clubs', label: 'Клубы' },
  ]

  return (
    <div className="mx-auto max-w-4xl px-5 py-12">
      <div className="text-center">
        <p className="font-mono text-xs font-medium uppercase tracking-[0.25em] text-rust/80">Итоговый зачёт</p>
        <h1 className="mt-3 font-display text-4xl font-bold leading-tight text-bone sm:text-5xl">
          Рейтинги
        </h1>
      </div>

      <div className="mt-8 flex justify-center gap-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`text-eyebrow rounded-xl px-4 py-2 transition-all duration-300 ${
              tab === t.key
                ? 'bg-gradient-to-br from-petrol/80 to-petrol-2/60 text-bone shadow-[0_4px_20px_-4px_rgba(18,54,59,0.4)]'
                : 'border border-steel-dim/20 text-steel-dim hover:border-steel-dim/40 hover:text-steel'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-8">
        {tab === 'athletes' && (
          <>
            <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="relative flex-1 max-w-xs">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Поиск по имени..."
                  className="w-full rounded-xl border border-steel-dim/20 bg-ink/80 px-4 py-2.5 pl-10 text-sm text-bone placeholder:text-steel-dim/50 backdrop-blur transition-colors focus:border-brass/50 focus:bg-ink focus:outline-none"
                />
                <svg className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-dim" viewBox="0 0 16 16" fill="none">
                  <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.3" />
                  <path d="M11 11l3.5 3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                </svg>
              </div>
              <div className="flex gap-1.5 rounded-xl border border-steel-dim/15 bg-ink/40 p-1">
                {handOptions.map((o) => (
                  <button
                    key={o.value}
                    onClick={() => setHand(o.value)}
                    className={`rounded-lg px-3.5 py-1.5 font-mono text-xs font-medium transition-all duration-200 ${
                      hand === o.value
                        ? 'bg-petrol text-bone shadow-sm'
                        : 'text-steel-dim hover:text-steel'
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            {elo.isLoading && <LoadingState label="Загрузка рейтинга" />}
            {elo.isError && <ErrorState message={(elo.error as Error).message} onRetry={() => elo.refetch()} />}
            {elo.data && elo.data.length === 0 && <EmptyState title="Никого не нашли" message="Попробуйте изменить параметры поиска." />}
            {elo.data && elo.data.length > 0 && (
              <div className="space-y-3">
                {elo.data.map((r) => {
                  const displayElo = hand === 'left' ? r.elo_left : hand === 'right' ? r.elo_right : r.elo_combined
                  return (
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
                            {r.club_name && <span className="truncate">{r.club_name}</span>}
                          </div>
                        </div>
                        <div className="flex flex-col items-end">
                          <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-rust/60">Rating</span>
                          <span className="font-display text-xl font-bold text-rust sm:text-2xl">{displayElo}</span>
                        </div>
                      </div>
                    </Link>
                  )
                })}
              </div>
            )}
          </>
        )}

        {tab === 'coaches' && (
          <>
            {coaches.isLoading && <LoadingState label="Загрузка рейтинга" />}
            {coaches.isError && <ErrorState message={(coaches.error as Error).message} onRetry={() => coaches.refetch()} />}
            {coaches.data && coaches.data.length === 0 && (
              <EmptyState title="Рейтинг ещё не сформирован" message="Рейтинг тренеров считается по сумме очков их учеников." />
            )}
            {coaches.data && coaches.data.length > 0 && (
              <div className="space-y-3">
                {coaches.data.map((r) => (
                  <Link
                    key={r.coach_id}
                    to={`/coaches/${r.coach_id}`}
                    className="group relative block overflow-hidden rounded-2xl border border-steel-dim/15 bg-gradient-to-br from-petrol/30 to-ink-soft/70 p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-brass/25 hover:shadow-[0_8px_30px_-6px_rgba(201,162,39,0.1)] sm:p-5"
                  >
                    <div className="pointer-events-none absolute -right-12 -top-12 h-28 w-28 rounded-full bg-brass/5 blur-3xl transition-all duration-500 group-hover:bg-brass/10" />
                    <div className="flex items-center gap-4">
                      <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl font-display text-sm font-bold transition-all ${
                        (r.position ?? 0) <= 3
                          ? (r.position ?? 0) === 1
                            ? 'bg-gradient-to-br from-yellow-500/20 to-yellow-600/10 text-yellow-400'
                            : (r.position ?? 0) === 2
                              ? 'bg-gradient-to-br from-slate-300/20 to-slate-400/10 text-slate-300'
                              : 'bg-gradient-to-br from-amber-700/20 to-amber-800/10 text-amber-600'
                          : 'bg-ink/60 text-steel-dim'
                      }`}>{r.position ?? 0}</div>
                      <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl border border-steel-dim/15 bg-ink font-display text-sm text-steel-dim transition-all group-hover:border-brass/30">
                        {r.coach_name.charAt(0)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-display text-base font-semibold text-bone transition-colors group-hover:text-brass sm:text-lg">
                          {r.coach_name}
                        </div>
                        <div className="mt-0.5 font-mono text-xs text-steel-dim">
                          {r.club_name ?? '—'} · {r.athletes_count} учен.
                        </div>
                      </div>
                      <div className="flex flex-col items-end">
                        <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-rust/60">Рейтинг</span>
                        <span className="font-display text-xl font-bold text-rust sm:text-2xl">{r.points}</span>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}

        {tab === 'clubs' && (
          <>
            {clubs.isLoading && <LoadingState label="Загрузка рейтинга" />}
            {clubs.isError && <ErrorState message={(clubs.error as Error).message} onRetry={() => clubs.refetch()} />}
            {clubs.data && clubs.data.length === 0 && <EmptyState title="Рейтинг ещё не сформирован" />}
            {clubs.data && clubs.data.length > 0 && (
              <div className="space-y-3">
                {clubs.data.map((r) => (
                  <div key={r.club_id} className="group relative block overflow-hidden rounded-2xl border border-steel-dim/15 bg-gradient-to-br from-petrol/30 to-ink-soft/70 p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-brass/25 hover:shadow-[0_8px_30px_-6px_rgba(201,162,39,0.1)] sm:p-5">
                    <div className="pointer-events-none absolute -right-12 -top-12 h-28 w-28 rounded-full bg-brass/5 blur-3xl transition-all duration-500 group-hover:bg-brass/10" />
                    <div className="flex items-center gap-4">
                      <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl font-display text-sm font-bold ${
                        (r.position ?? 0) <= 3
                          ? (r.position ?? 0) === 1
                            ? 'bg-gradient-to-br from-yellow-500/20 to-yellow-600/10 text-yellow-400'
                            : (r.position ?? 0) === 2
                              ? 'bg-gradient-to-br from-slate-300/20 to-slate-400/10 text-slate-300'
                              : 'bg-gradient-to-br from-amber-700/20 to-amber-800/10 text-amber-600'
                          : 'bg-ink/60 text-steel-dim'
                      }`}>{r.position ?? 0}</div>
                      <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl border border-steel-dim/15 bg-ink font-display text-sm text-steel-dim transition-all group-hover:border-brass/30">
                        {r.club_name.charAt(0)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-display text-base font-semibold text-bone sm:text-lg">
                          {r.club_name}
                        </div>
                        <div className="mt-0.5 font-mono text-xs text-steel-dim">
                          {r.gold_count} · {r.silver_count} · {r.bronze_count}
                        </div>
                      </div>
                      <div className="flex flex-col items-end">
                        <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-brass/60">Очки</span>
                        <span className="font-display text-xl font-bold text-brass sm:text-2xl">{r.points}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}