import { Link, useParams } from 'react-router-dom'
import { useCoach } from '@/features/coaches/useCoaches'
import { useAthletes } from '@/features/athletes/useAthletes'
import { AthleteCard } from '@/components/ui/AthleteCard'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'

function age(birthDate: string | null): number | null {
  if (!birthDate) return null
  const b = new Date(birthDate)
  const diff = Date.now() - b.getTime()
  return Math.floor(diff / (365.25 * 24 * 60 * 60 * 1000))
}

export function CoachProfile() {
  const { id } = useParams<{ id: string }>()
  const coachId = Number(id)

  const coach = useCoach(coachId)
  const athletes = useAthletes({ coach_id: coachId, page_size: 50 })

  if (coach.isLoading) return <LoadingState label="Загрузка профиля" />
  if (coach.isError) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <ErrorState
          title="Тренер не найден"
          message={(coach.error as Error).message}
          onRetry={() => coach.refetch()}
        />
      </div>
    )
  }
  if (!coach.data) return null

  const c = coach.data
  const a = age(c.birth_date)

  return (
    <div className="mx-auto max-w-5xl px-5 py-12">
      <Link to="/coaches" className="text-sm text-steel hover:text-brass">
        ← ко всем тренерам
      </Link>

      <div className="plate mt-4 flex flex-col gap-6 rounded-[var(--radius-rivet)] p-6 sm:flex-row sm:items-center">
        <div className="flex h-24 w-24 flex-shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-rivet)] border-2 border-brass/50 bg-ink font-display text-2xl text-steel">
          {c.photo_path ? (
            <img src={c.photo_path} alt="" className="h-full w-full object-cover" />
          ) : (
            c.full_name
              .split(' ')
              .map((p) => p[0])
              .slice(0, 2)
              .join('')
          )}
        </div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl text-bone sm:text-3xl">{c.full_name}</h1>
            {c.qualification && (
              <span className="text-eyebrow rounded-[var(--radius-rivet)] border border-brass/40 px-2 py-1 text-brass">
                {c.qualification}
              </span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-sm text-steel">
            {a !== null && <span>{a} лет</span>}
            {c.city_name && <span>{c.city_name}</span>}
            {c.club_name && <span>Клуб: {c.club_name}</span>}
            <span>{c.athletes_count} спортсменов</span>
          </div>
        </div>
      </div>

      {c.bio && (
        <div className="plate mt-6 rounded-[var(--radius-rivet)] p-6">
          <h2 className="text-eyebrow text-rust">О тренере</h2>
          <p className="mt-2 whitespace-pre-line text-steel">{c.bio}</p>
        </div>
      )}

      <div className="mt-8">
        <h2 className="font-display text-xl text-bone">Спортсмены</h2>
        <div className="mt-4">
          {athletes.isLoading && <LoadingState label="Загрузка спортсменов" />}
          {athletes.isError && <ErrorState message={(athletes.error as Error).message} onRetry={() => athletes.refetch()} />}
          {athletes.data && athletes.data.items.length === 0 && (
            <EmptyState title="Пока нет учеников" message="У тренера ещё нет привязанных спортсменов." />
          )}
          {athletes.data && athletes.data.items.length > 0 && (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {athletes.data.items.map((ath) => (
                <AthleteCard key={ath.id} athlete={ath} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
