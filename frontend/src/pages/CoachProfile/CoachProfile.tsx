import { Link, useParams } from 'react-router-dom'
import { useCoach } from '@/features/coaches/useCoaches'
import { useAthletes } from '@/features/athletes/useAthletes'
import { AthleteCard } from '@/components/ui/AthleteCard'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { ageText } from '@/lib/age'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' })
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
  const at = ageText(c.birth_date)

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
          <Link to="/coaches" className="group inline-flex items-center gap-1.5 text-sm text-steel-dim transition-colors hover:text-brass">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="transition-transform group-hover:-translate-x-0.5">
              <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Ко всем тренерам
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
                  {c.photo_path ? (
                    <img
                      src={cloudinaryThumb(c.photo_path, 224) ?? c.photo_path}
                      alt=""
                      className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105"
                    />
                  ) : (
                    <span className="font-display text-3xl text-steel-dim sm:text-4xl">
                      {c.full_name.split(' ').map((p) => p[0]).slice(0, 2).join('')}
                    </span>
                  )}
                </div>
              </div>

              {/* Инфо */}
              <div className="flex-1 pt-1">
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="font-display text-3xl font-bold leading-tight text-bone sm:text-4xl lg:text-5xl">
                    {c.full_name}
                  </h1>
                  {c.qualification && (
                    <span className="order-first sm:order-none inline-flex items-center gap-1.5 rounded-full border border-brass/30 bg-brass/5 px-3 py-1 font-mono text-xs font-medium tracking-wider text-brass">
                      <span className="h-1.5 w-1.5 rounded-full bg-brass/60" />
                      {c.qualification}
                    </span>
                  )}
                </div>

                {/* Дата рождения · возраст */}
                {c.birth_date && (
                  <div className="mt-4 inline-flex items-center gap-2 font-mono text-sm text-steel">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-steel-dim">
                      <rect x="2" y="3" width="10" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                      <path d="M4.5 1.5V5M9.5 1.5V5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                      <path d="M2 6.5h10" stroke="currentColor" strokeWidth="1.2"/>
                    </svg>
                    {formatDate(c.birth_date)}
                    {at !== null && <span className="font-semibold text-bone">· {at}</span>}
                  </div>
                )}

                {/* Город · спортсмены */}
                <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-sm text-steel">
                  {c.city_name && (
                    <span className="inline-flex items-center gap-2">
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-steel-dim">
                        <path d="M7 1.5C5 1.5 3.5 3 3.5 5c0 3 3.5 7 3.5 7s3.5-4 3.5-7c0-2-1.5-3.5-3.5-3.5z" stroke="currentColor" strokeWidth="1.2"/>
                        <circle cx="7" cy="5" r="1.3" stroke="currentColor" strokeWidth="1.2"/>
                      </svg>
                      {c.city_name}
                    </span>
                  )}
                  <span className="inline-flex items-center gap-2">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-steel-dim">
                      <circle cx="7" cy="5" r="2.6" stroke="currentColor" strokeWidth="1.2"/>
                      <path d="M2 12.5c0-2.8 2.2-5 5-5s5 2.2 5 5" stroke="currentColor" strokeWidth="1.2"/>
                    </svg>
                    {c.athletes_count} спортсменов
                  </span>
                </div>

                {/* Клуб */}
                <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2 border-t border-steel-dim/15 pt-4">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-petrol-2/50">
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <path d="M2 14V6l6-4 6 4v8H2z" stroke="var(--color-steel)" strokeWidth="1.3"/>
                        <path d="M6 14V9h4v5" stroke="var(--color-steel)" strokeWidth="1.3"/>
                      </svg>
                    </div>
                    <div>
                      <div className="text-eyebrow text-steel-dim">Клуб</div>
                      {c.club_name ? (
                        <div className="text-sm font-medium text-bone">{c.club_name}</div>
                      ) : (
                        <div className="text-sm font-medium text-steel-dim">не состоит</div>
                      )}
                    </div>
                  </div>
                </div>

                {c.bio && (
                  <p className="mt-5 max-w-xl whitespace-pre-line leading-relaxed text-steel">{c.bio}</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Тело страницы */}
      <div className="mx-auto max-w-5xl px-5 py-10">
        <section>
          <div className="mb-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-brass/40 via-brass/10 to-transparent" />
            <h2 className="font-display text-lg font-semibold tracking-wide text-bone">Спортсмены</h2>
            <div className="h-px flex-1 bg-gradient-to-l from-brass/40 via-brass/10 to-transparent" />
          </div>

          {athletes.isLoading && <LoadingState label="Загрузка спортсменов" />}
          {athletes.isError && <ErrorState message={(athletes.error as Error).message} onRetry={() => athletes.refetch()} />}
          {athletes.data && athletes.data.items.length === 0 && (
            <EmptyState title="Пока нет учеников" message="У тренера ещё нет привязанных спортсменов." />
          )}
          {athletes.data && athletes.data.items.length > 0 && (
            <div className="grid gap-5 sm:grid-cols-2 2xl:grid-cols-3">
              {athletes.data.items.map((ath) => (
                <AthleteCard key={ath.id} athlete={ath} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
