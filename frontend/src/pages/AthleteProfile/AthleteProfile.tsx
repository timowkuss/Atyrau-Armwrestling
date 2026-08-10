import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAthlete, useAthleteEloHistory, useAthleteHistory, useAthleteMatches } from '@/features/athletes/useAthletes'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { Gauge } from '@/components/ui/Gauge'
import { EloRating } from '@/components/ui/EloRating'
import { MedalBadge } from '@/components/ui/Medal'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { ageText } from '@/lib/age'
import type { EloHistoryItem } from '@/types/api'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' })
}

function EloHistorySection({ items }: { items: EloHistoryItem[] }) {
  const rows = useMemo(() => {
    const map = new Map<number, { competition_id: number; competition_name: string; date: string; left?: number; right?: number; both?: number }>()
    for (const it of items) {
      const row = map.get(it.competition_id) ?? { competition_id: it.competition_id, competition_name: it.competition_name, date: it.date }
      if (it.hand === 'left') row.left = it.elo
      if (it.hand === 'right') row.right = it.elo
      if (it.hand === 'both') row.both = it.elo
      map.set(it.competition_id, row)
    }
    return [...map.values()].sort((a, b) => a.date.localeCompare(b.date))
  }, [items])

  const delta = (current: number | undefined, i: number, key: 'left' | 'right' | 'both') => {
    if (current == null) return null
    const prev = rows[i - 1]?.[key]
    if (prev == null || prev === current) return null
    const d = current - prev
    return d > 0 ? `+${d}` : `${d}`
  }

  const Cell = ({ value, d }: { value: number | undefined; d: string | null }) => (
    <td className="px-4 py-3 font-mono text-sm">
      {value == null ? (
        <span className="text-steel-dim">—</span>
      ) : (
        <div className="flex items-baseline gap-2">
          <span className="text-bone">{value}</span>
          {d && <span className={`text-xs font-semibold ${d.startsWith('+') ? 'text-brass' : 'text-rust'}`}>{d}</span>}
        </div>
      )}
    </td>
  )

  return (
    <section className="mt-14">
      <div className="mb-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-gradient-to-r from-brass/40 via-brass/10 to-transparent" />
        <h2 className="font-display text-lg font-semibold tracking-wide text-bone">История рейтинга</h2>
        <div className="h-px flex-1 bg-gradient-to-l from-brass/40 via-brass/10 to-transparent" />
      </div>

      <div className="overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-b from-petrol/30 to-ink-soft/50">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-steel-dim/15">
                <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Турнир</th>
                <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Дата</th>
                <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Левая</th>
                <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Правая</th>
                <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Общий</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.competition_name}-${r.date}`} className="border-b border-steel-dim/10 transition-colors last:border-none hover:bg-bone/[0.02]">
                  <td className="px-5 py-3.5">
                    <Link to={`/competitions/${r.competition_id}`} className="font-medium text-bone transition-colors hover:text-brass">
                      {r.competition_name}
                    </Link>
                  </td>
                  <td className="px-5 py-3.5 font-mono text-sm text-steel">{formatDate(r.date)}</td>
                  <Cell value={r.left} d={delta(r.left, i, 'left')} />
                  <Cell value={r.right} d={delta(r.right, i, 'right')} />
                  <Cell value={r.both} d={delta(r.both, i, 'both')} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

export function AthleteProfile() {
  const { id } = useParams<{ id: string }>()
  const athleteId = Number(id)

  const athlete = useAthlete(athleteId)
  const history = useAthleteHistory(athleteId)
  const matches = useAthleteMatches(athleteId)
  const eloHistory = useAthleteEloHistory(athleteId)

  if (athlete.isLoading) return <LoadingState label="Загрузка профиля" />
  if (athlete.isError) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <ErrorState
          title="Спортсмен не найден"
          message={(athlete.error as Error).message}
          onRetry={() => athlete.refetch()}
        />
      </div>
    )
  }
  if (!athlete.data) return null

  const a = athlete.data
  const stats = a.statistics

  return (
    <div className="relative">
      {/* Hero section — параллакс-градиент, фото на всю ширину */}
      <div className="relative overflow-hidden border-b border-steel-dim/20">
        <div className="pointer-events-none absolute inset-0 -z-10"
          style={{
            background: `
              radial-gradient(1100px 500px at 70% 20%, rgba(201,162,39,0.10), transparent 60%),
              radial-gradient(800px 600px at 10% 80%, rgba(193,85,44,0.08), transparent 55%),
              radial-gradient(600px 400px at 50% 50%, rgba(18,54,59,0.6), transparent 70%)
            `
          }}
        />
        <div className="mx-auto max-w-5xl px-5 pb-16 pt-8 sm:pt-12">
          <Link to="/athletes" className="group inline-flex items-center gap-1.5 text-sm text-steel-dim transition-colors hover:text-brass">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="transition-transform group-hover:-translate-x-0.5">
              <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Назад к списку
          </Link>

          {/* Hero card — стеклянная панель с фото */}
          <div className="relative mt-6 overflow-hidden rounded-2xl border border-steel-dim/20 bg-gradient-to-br from-petrol/70 via-ink-soft/80 to-ink/90 backdrop-blur">
            <div className="pointer-events-none absolute inset-0 -z-10"
              style={{
                background: 'radial-gradient(600px 300px at 30% 40%, rgba(201,162,39,0.06), transparent 70%)'
              }}
            />
            <div className="flex flex-col gap-8 p-6 sm:flex-row sm:items-start sm:p-8 lg:p-10">
              {/* Фото */}
              <div className="group relative flex-shrink-0">
                <div className="absolute -inset-1 rounded-2xl bg-gradient-to-br from-brass/30 to-rust/30 opacity-0 blur transition-opacity duration-500 group-hover:opacity-100" />
                <div className="relative flex h-40 w-40 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-brass/30 bg-ink sm:h-56 sm:w-56">
                  {a.photo_path ? (
                    <img
                      src={cloudinaryThumb(a.photo_path, 224) ?? a.photo_path}
                      alt=""
                      className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105"
                    />
                  ) : (
                    <span className="font-display text-3xl text-steel-dim sm:text-4xl">
                      {a.full_name.split(' ').map((p) => p[0]).slice(0, 2).join('')}
                    </span>
                  )}
                </div>
              </div>

              {/* Инфо */}
              <div className="flex-1 pt-1">
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="font-display text-3xl font-bold leading-tight text-bone sm:text-4xl lg:text-5xl">
                    {a.full_name}
                  </h1>
                  {a.rank && (
                    <span className="order-first sm:order-none inline-flex items-center gap-1.5 rounded-full border border-brass/30 bg-brass/5 px-3 py-1 font-mono text-xs font-medium tracking-wider text-brass">
                      <span className="h-1.5 w-1.5 rounded-full bg-brass/60" />
                      {a.rank}
                    </span>
                  )}
                </div>

                {/* Пол · город                рейтинг */}
                <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-wrap items-center gap-x-5 gap-y-2 font-mono text-sm text-steel">
                    <span className="inline-flex items-center gap-2">
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-steel-dim">
                        <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.2"/>
                        <circle cx="7" cy="5" r="1.6" fill="currentColor"/>
                        <path d="M7 7c-1.5 0-2.5 1-2.5 2.5 0 .8.4 1.3 1 1.8a5 5 0 013 0c.6-.5 1-1 1-1.8C9.5 8 8.5 7 7 7z" fill="currentColor" opacity="0.45"/>
                      </svg>
                      {a.gender === 'male' ? 'Мужчины' : 'Женщины'}
                    </span>
                    {a.city_name && (
                      <span className="inline-flex items-center gap-2">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-steel-dim">
                          <path d="M7 1.5C5 1.5 3.5 3 3.5 5c0 3 3.5 7 3.5 7s3.5-4 3.5-7c0-2-1.5-3.5-3.5-3.5z" stroke="currentColor" strokeWidth="1.2"/>
                          <circle cx="7" cy="5" r="1.3" stroke="currentColor" strokeWidth="1.2"/>
                        </svg>
                        {a.city_name}{a.region_name ? `, ${a.region_name}` : ''}
                      </span>
                    )}
                  </div>
                  {stats && (
                    <span className="inline-flex flex-shrink-0 flex-col items-end gap-0.5">
                      <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-rust/60">Rating</span>
                      <span className="font-display text-3xl font-bold leading-none text-rust">{stats.elo_combined}</span>
                    </span>
                  )}
                </div>

                {/* Год рождения · возраст */}
                {a.birth_date && (
                  <div className="mt-3 inline-flex items-center gap-2 font-mono text-sm text-steel">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-steel-dim">
                      <rect x="2" y="3" width="10" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                      <path d="M4.5 1.5V5M9.5 1.5V5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                      <path d="M2 6.5h10" stroke="currentColor" strokeWidth="1.2"/>
                    </svg>
                    {formatDate(a.birth_date)}
                    {ageText(a.birth_date) !== null && (
                      <span className="font-semibold text-bone">· {ageText(a.birth_date)}</span>
                    )}
                  </div>
                )}

                {/* Тренер · клуб */}
                <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2 border-t border-steel-dim/15 pt-4">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-petrol-2/50">
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <circle cx="8" cy="5" r="3" stroke="var(--color-steel)" strokeWidth="1.3"/>
                        <path d="M3 14c0-3 2.5-5.5 5-5.5s5 2.5 5 5.5" stroke="var(--color-steel)" strokeWidth="1.3"/>
                      </svg>
                    </div>
                    <div>
                      <div className="text-eyebrow text-steel-dim">Тренер</div>
                      {a.coach_name ? (
                        a.coach_id ? (
                          <Link to={`/coaches/${a.coach_id}`} className="text-sm font-medium text-bone transition-colors hover:text-brass">
                            {a.coach_name}
                          </Link>
                        ) : (
                          <div className="text-sm font-medium text-bone">{a.coach_name}</div>
                        )
                      ) : (
                        <div className="text-sm font-medium text-steel-dim">отсутствует</div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-petrol-2/50">
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M2 14V6l6-4 6 4v8H2z" stroke="var(--color-steel)" strokeWidth="1.3"/>
                        <path d="M6 14V9h4v5" stroke="var(--color-steel)" strokeWidth="1.3"/>
                      </svg>
                    </div>
                    <div>
                      <div className="text-eyebrow text-steel-dim">Клуб</div>
                      {a.club_name ? (
                        a.club_id ? (
                          <Link
                            to={`/clubs/${a.club_id}`}
                            className="text-sm font-medium text-bone underline decoration-steel-dim/30 underline-offset-2 transition-colors hover:text-brass hover:decoration-brass/50"
                          >
                            {a.club_name}
                          </Link>
                        ) : (
                          <div className="text-sm font-medium text-bone">{a.club_name}</div>
                        )
                      ) : (
                        <div className="text-sm font-medium text-steel-dim">не состоит</div>
                      )}
                    </div>
                  </div>
                </div>

                {a.bio && (
                  <p className="mt-5 max-w-xl leading-relaxed text-steel">{a.bio}</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Тело страницы */}
      <div className="mx-auto max-w-5xl px-5 py-10">
        {/* Статистика */}
        {stats && (
          <section>
            <div className="mb-6 flex items-center gap-3">
              <div className="h-px flex-1 bg-gradient-to-r from-brass/40 via-brass/10 to-transparent" />
              <h2 className="font-display text-lg font-semibold tracking-wide text-bone">Статистика</h2>
              <div className="h-px flex-1 bg-gradient-to-l from-brass/40 via-brass/10 to-transparent" />
            </div>

            <div className="mb-6">
              <EloRating eloLeft={stats.elo_left} eloRight={stats.elo_right} eloCombined={stats.elo_combined} />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="group relative overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/60 p-5 transition-all duration-300 hover:border-brass/30 hover:shadow-[0_0_30px_-6px_rgba(201,162,39,0.15)]">
                <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-brass/5 blur-2xl transition-all duration-500 group-hover:bg-brass/10" />
                <Gauge value={stats.win_rate * 100} label="Побед" sublabel={`${stats.total_wins}–${stats.total_losses}`} size={96} />
              </div>

              <div className="group relative overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/60 p-5 transition-all duration-300 hover:border-brass/30 hover:shadow-[0_0_30px_-6px_rgba(201,162,39,0.15)]">
                <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-brass/5 blur-2xl transition-all duration-500 group-hover:bg-brass/10" />
                <div className="flex h-full flex-col items-center justify-center gap-1 pt-4">
                  <span className="font-display text-3xl font-bold text-bone">{stats.total_competitions}</span>
                  <span className="text-eyebrow text-steel">турниров</span>
                </div>
              </div>

              <div className="group relative overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/60 p-5 transition-all duration-300 hover:border-brass/30 hover:shadow-[0_0_30px_-6px_rgba(201,162,39,0.15)]">
                <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-brass/5 blur-2xl transition-all duration-500 group-hover:bg-brass/10" />
                <div className="flex h-full flex-col items-center justify-center gap-1 pt-4">
                  <div className="flex items-center gap-2">
                    <span className="font-display text-xl font-bold text-brass sm:text-2xl">{stats.gold_count}</span>
                    <span className="text-steel-dim">·</span>
                    <span className="font-display text-xl font-bold text-steel sm:text-2xl">{stats.silver_count}</span>
                    <span className="text-steel-dim">·</span>
                    <span className="font-display text-xl font-bold text-rust sm:text-2xl">{stats.bronze_count}</span>
                  </div>
                  <span className="text-eyebrow text-steel">медали</span>
                </div>
              </div>

              <div className="group relative overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/60 p-5 transition-all duration-300 hover:border-brass/30 hover:shadow-[0_0_30px_-6px_rgba(201,162,39,0.15)]">
                <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-brass/5 blur-2xl transition-all duration-500 group-hover:bg-brass/10" />
                <div className="flex h-full flex-col items-center justify-center gap-2 pt-2">
                  <div className="flex w-full justify-around font-mono text-xs sm:text-sm">
                    <div className="flex flex-col items-center gap-0.5">
                      <span className="text-eyebrow text-steel-dim">L</span>
                      <span className="font-medium text-bone">{stats.left_hand_wins}–{stats.left_hand_losses}</span>
                    </div>
                    <div className="w-px bg-steel-dim/20" />
                    <div className="flex flex-col items-center gap-0.5">
                      <span className="text-eyebrow text-steel-dim">R</span>
                      <span className="font-medium text-bone">{stats.right_hand_wins}–{stats.right_hand_losses}</span>
                    </div>
                  </div>
                  <span className="text-eyebrow text-steel">по руке</span>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* История рейтинга */}
        {eloHistory.data && eloHistory.data.items.length > 0 && (
          <EloHistorySection items={eloHistory.data.items} />
        )}

        {/* История турниров */}
        <section className="mt-14">
          <div className="mb-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-rust/40 via-rust/10 to-transparent" />
            <h2 className="font-display text-lg font-semibold tracking-wide text-bone">История турниров</h2>
            <div className="h-px flex-1 bg-gradient-to-l from-rust/40 via-rust/10 to-transparent" />
          </div>

          {history.isLoading && <LoadingState label="Загрузка истории" />}
          {history.isError && <ErrorState message={(history.error as Error).message} onRetry={() => history.refetch()} />}
          {history.data && history.data.length === 0 && (
            <EmptyState title="Пока нет опубликованных турниров" />
          )}
          {history.data && history.data.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-b from-petrol/30 to-ink-soft/50">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-steel-dim/15">
                      <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Турнир</th>
                      <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Дата</th>
                      <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Категория</th>
                      <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Место</th>
                      <th className="px-5 py-3.5 font-mono text-xs font-medium uppercase tracking-widest text-steel-dim">Медаль</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.data.map((h, i) => (
                      <tr key={i} className="border-b border-steel-dim/10 transition-colors hover:bg-bone/[0.02] last:border-none">
                        <td className="px-5 py-3.5">
                          <Link to={`/competitions/${h.competition_id}`} className="font-medium text-bone transition-colors hover:text-brass">
                            {h.competition_name}
                          </Link>
                        </td>
                        <td className="px-5 py-3.5 font-mono text-sm text-steel">{formatDate(h.date)}</td>
                        <td className="px-5 py-3.5 text-steel">{h.category_name}</td>
                        <td className="px-5 py-3.5 font-mono text-sm font-medium text-bone">{h.place ?? '—'}</td>
                        <td className="px-5 py-3.5">
                          <MedalBadge medal={h.medal} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        {/* Последние матчи */}
        <section className="mt-14 mb-20">
          <div className="mb-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-steel-dim/30 via-steel-dim/10 to-transparent" />
            <h2 className="font-display text-lg font-semibold tracking-wide text-bone">Последние матчи</h2>
            <div className="h-px flex-1 bg-gradient-to-l from-steel-dim/30 via-steel-dim/10 to-transparent" />
          </div>

          {matches.isLoading && <LoadingState label="Загрузка матчей" />}
          {matches.isError && <ErrorState message={(matches.error as Error).message} onRetry={() => matches.refetch()} />}
          {matches.data && matches.data.length === 0 && <EmptyState title="Матчей пока нет" />}
          {matches.data && matches.data.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-b from-petrol/30 to-ink-soft/50">
              <div className="divide-y divide-steel-dim/10">
                {matches.data.map((m) => (
                  <div key={m.match_id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 transition-colors hover:bg-bone/[0.02]">
                    <div className="min-w-0 flex-1">
                      <Link to={`/competitions/${m.competition_id}`} className="font-medium text-bone transition-colors hover:text-brass">
                        {m.competition_name}
                      </Link>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-xs text-steel-dim">
                        {m.category_name && <span>{m.category_name}</span>}
                        {m.round_name && <span className="inline-flex items-center gap-1"><span className="h-1 w-1 rounded-full bg-steel-dim/40" />{m.round_name}</span>}
                        {m.opponent_name && <span className="inline-flex items-center gap-1"><span className="h-1 w-1 rounded-full bg-steel-dim/40" />vs {m.opponent_name}</span>}
                      </div>
                    </div>
                    {m.is_winner === null ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-steel-dim/20 px-3 py-1 font-mono text-xs text-steel-dim">
                        <span className="h-1.5 w-1.5 rounded-full bg-steel-dim/40" />
                        не завершён
                      </span>
                    ) : (
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-xs font-medium ${
                          m.is_winner
                            ? 'border border-success/30 bg-success/10 text-success'
                            : 'border border-danger/30 bg-danger/10 text-danger'
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${m.is_winner ? 'bg-success' : 'bg-danger'}`} />
                        {m.is_winner ? 'победа' : 'поражение'}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
