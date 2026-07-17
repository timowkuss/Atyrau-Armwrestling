import { Link, useParams } from 'react-router-dom'
import { useAthlete, useAthleteHistory, useAthleteMatches } from '@/features/athletes/useAthletes'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { Gauge } from '@/components/ui/Gauge'
import { MedalBadge } from '@/components/ui/Medal'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function AthleteProfile() {
  const { id } = useParams<{ id: string }>()
  const athleteId = Number(id)

  const athlete = useAthlete(athleteId)
  const history = useAthleteHistory(athleteId)
  const matches = useAthleteMatches(athleteId)

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
    <div className="mx-auto max-w-5xl px-5 py-12">
      <Link to="/athletes" className="text-sm text-steel hover:text-brass">
        ← ко всем спортсменам
      </Link>

      {/* Заголовок профиля */}
      <div className="plate mt-4 flex flex-col gap-6 rounded-[var(--radius-rivet)] p-6 sm:flex-row sm:items-center">
        <div className="flex h-24 w-24 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-brass/50 bg-ink font-display text-2xl text-steel">
          {a.photo_path ? (
            <img src={a.photo_path} alt="" className="h-full w-full object-cover" />
          ) : (
            a.full_name
              .split(' ')
              .map((p) => p[0])
              .slice(0, 2)
              .join('')
          )}
        </div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl text-bone sm:text-3xl">{a.full_name}</h1>
            {a.rank && (
              <span className="text-eyebrow rounded-[var(--radius-rivet)] border border-brass/40 px-2 py-1 text-brass">
                {a.rank}
              </span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-sm text-steel">
            <span>{a.gender === 'male' ? 'мужчины' : 'женщины'}</span>
            {a.birth_date && <span>{formatDate(a.birth_date)}</span>}
            {a.city_name && <span>{a.city_name}</span>}
            {a.region_name && <span>{a.region_name}</span>}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm text-steel-dim">
            {a.club_name && <span>Клуб: <span className="text-bone">{a.club_name}</span></span>}
            {a.coach_name && <span>Тренер: <span className="text-bone">{a.coach_name}</span></span>}
          </div>
          {a.bio && <p className="mt-3 max-w-2xl text-sm text-steel">{a.bio}</p>}
        </div>
      </div>

      {/* Статистика — циферблаты */}
      {stats && (
        <section className="mt-8">
          <h2 className="font-display text-xl text-bone">Статистика</h2>
          <div className="rivet-line my-4" />
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <div className="plate flex flex-col items-center rounded-[var(--radius-rivet)] p-4">
              <Gauge value={stats.win_rate * 100} label="Побед" sublabel={`${stats.total_wins}–${stats.total_losses}`} size={120} />
            </div>
            <div className="plate flex flex-col items-center justify-center gap-1 rounded-[var(--radius-rivet)] p-4">
              <span className="font-display text-2xl text-bone">{stats.total_competitions}</span>
              <span className="text-eyebrow text-steel">турниров</span>
            </div>
            <div className="plate flex flex-col items-center justify-center gap-1 rounded-[var(--radius-rivet)] p-4">
              <span className="font-display text-2xl text-brass">{stats.gold_count}·{stats.silver_count}·{stats.bronze_count}</span>
              <span className="text-eyebrow text-steel">золото·серебро·бронза</span>
            </div>
            <div className="plate flex flex-col items-center justify-center gap-1 rounded-[var(--radius-rivet)] p-4 font-mono text-xs text-steel">
              <span className="text-bone">L {stats.left_hand_wins}–{stats.left_hand_losses}</span>
              <span className="text-bone">R {stats.right_hand_wins}–{stats.right_hand_losses}</span>
              <span className="text-eyebrow mt-1 text-steel">по руке</span>
            </div>
          </div>
        </section>
      )}

      {/* История турниров */}
      <section className="mt-10">
        <h2 className="font-display text-xl text-bone">История турниров</h2>
        <div className="rivet-line my-4" />
        {history.isLoading && <LoadingState label="Загрузка истории" />}
        {history.isError && <ErrorState message={(history.error as Error).message} onRetry={() => history.refetch()} />}
        {history.data && history.data.length === 0 && (
          <EmptyState title="Пока нет опубликованных турниров" />
        )}
        {history.data && history.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="text-eyebrow border-b border-steel-dim/40 text-steel">
                  <th className="py-2 pr-4">Турнир</th>
                  <th className="py-2 pr-4">Дата</th>
                  <th className="py-2 pr-4">Категория</th>
                  <th className="py-2 pr-4">Место</th>
                  <th className="py-2">Медаль</th>
                </tr>
              </thead>
              <tbody>
                {history.data.map((h, i) => (
                  <tr key={i} className="border-b border-steel-dim/15">
                    <td className="py-2.5 pr-4">
                      <Link to={`/competitions/${h.competition_id}`} className="text-bone hover:text-brass">
                        {h.competition_name}
                      </Link>
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-steel">{formatDate(h.date)}</td>
                    <td className="py-2.5 pr-4 text-steel">{h.category_name}</td>
                    <td className="py-2.5 pr-4 font-mono text-bone">{h.place ?? '—'}</td>
                    <td className="py-2.5">
                      <MedalBadge medal={h.medal} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* История матчей */}
      <section className="mt-10 mb-16">
        <h2 className="font-display text-xl text-bone">Последние матчи</h2>
        <div className="rivet-line my-4" />
        {matches.isLoading && <LoadingState label="Загрузка матчей" />}
        {matches.isError && <ErrorState message={(matches.error as Error).message} onRetry={() => matches.refetch()} />}
        {matches.data && matches.data.length === 0 && <EmptyState title="Матчей пока нет" />}
        {matches.data && matches.data.length > 0 && (
          <ul className="flex flex-col divide-y divide-steel-dim/15">
            {matches.data.map((m) => (
              <li key={m.match_id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div>
                  <Link to={`/competitions/${m.competition_id}`} className="text-sm text-bone hover:text-brass">
                    {m.competition_name}
                  </Link>
                  <div className="font-mono text-xs text-steel">
                    {m.category_name}
                    {m.round_name ? ` · ${m.round_name}` : ''}
                    {m.opponent_name ? ` · vs ${m.opponent_name}` : ''}
                  </div>
                </div>
                {m.is_winner === null ? (
                  <span className="font-mono text-xs text-steel-dim">не завершён</span>
                ) : (
                  <span
                    className={`text-eyebrow rounded-[var(--radius-rivet)] px-2 py-1 ${
                      m.is_winner ? 'bg-success/15 text-success' : 'bg-danger/15 text-danger'
                    }`}
                  >
                    {m.is_winner ? 'победа' : 'поражение'}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
