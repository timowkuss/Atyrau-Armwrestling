import { Link, useParams } from 'react-router-dom'
import { useClub, useClubRating } from '@/features/clubs/useClubs'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { cloudinaryLogo, cloudinaryThumb } from '@/lib/cloudinaryImage'
import type { ClubMember, ClubRatingHistoryItem } from '@/types/api'

function initials(name: string): string {
  return name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  if (!y || !m || !d) return iso
  return `${d}.${m}.${y}`
}

function MemberAvatar({ member }: { member: ClubMember }) {
  return (
    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-rivet)] border border-steel-dim bg-ink font-display text-xs text-steel">
      {member.photo_path ? (
        <img
          src={cloudinaryThumb(member.photo_path, 40) ?? member.photo_path}
          alt=""
          className="h-full w-full object-cover"
          loading="lazy"
        />
      ) : (
        initials(member.full_name)
      )}
    </div>
  )
}

function MemberList({
  title,
  subtitle,
  members,
  linkPrefix,
  emptyMessage,
}: {
  title: string
  subtitle: string
  members: ClubMember[]
  linkPrefix: string
  emptyMessage: string
}) {
  return (
    <div className="plate rounded-[var(--radius-rivet)] p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-xl text-bone">{title}</h2>
        <span className="text-eyebrow text-steel">{members.length}</span>
      </div>
      <p className="mt-1 text-xs text-steel-dim">{subtitle}</p>

      {members.length === 0 ? (
        <EmptyState title={emptyMessage} />
      ) : (
        <ul className="mt-4 grid gap-2 sm:grid-cols-2">
          {members.map((m) => (
            <li key={m.id}>
              <Link
                to={`${linkPrefix}/${m.id}`}
                className="flex items-center gap-3 rounded-[var(--radius-rivet)] border border-steel-dim/40 bg-ink/60 px-3 py-2.5 transition-colors hover:border-brass/50 hover:bg-ink"
              >
                <MemberAvatar member={m} />
                <span className="truncate text-sm text-bone group-hover:text-brass">{m.full_name}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function RatingHistory({ items }: { items: ClubRatingHistoryItem[] }) {
  const fmtDate = (iso: string) => {
    const [d, m, y] = iso.split('T')[0].split('-')
    return d && m && y ? `${d}.${m}.${y}` : iso
  }

  return (
    <div className="plate rounded-[var(--radius-rivet)] p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-xl text-bone">История рейтинга</h2>
        <span className="text-eyebrow text-steel">{items.length}</span>
      </div>
      <p className="mt-1 text-xs text-steel-dim">
        Начисление баллов клубу за выступления спортсменов и изменения состава
      </p>

      {items.length === 0 ? (
        <EmptyState title="Пока нет записей" />
      ) : (
        <ul className="mt-4 divide-y divide-steel-dim/20">
          {items.map((h) => (
            <li key={h.id} className="flex items-start gap-3 py-2.5">
              <span
                className={`mt-0.5 w-14 flex-shrink-0 text-right font-mono text-sm font-semibold ${
                  h.points >= 0 ? 'text-brass' : 'text-rust'
                }`}
              >
                {h.points >= 0 ? `+${h.points}` : h.points}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-bone">{h.description}</div>
                <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-steel-dim">
                  {h.athlete_name && <span>{h.athlete_name}</span>}
                  {h.tournament_name && <span>🏆 {h.tournament_name}</span>}
                  <span>{fmtDate(h.created_at)}</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ClubProfile() {
  const { id } = useParams<{ id: string }>()
  const clubId = Number(id)

  const club = useClub(clubId)
  const rating = useClubRating(clubId)

  if (club.isLoading) return <LoadingState label="Загрузка клуба" />
  if (club.isError) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <ErrorState
          title="Клуб не найден"
          message={(club.error as Error).message}
          onRetry={() => club.refetch()}
        />
      </div>
    )
  }
  if (!club.data) return null

  const c = club.data

  return (
    <div className="relative">
      {/* Hero section */}
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
          <Link to="/clubs" className="group inline-flex items-center gap-1.5 text-sm text-steel-dim transition-colors hover:text-brass">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="transition-transform group-hover:-translate-x-0.5">
              <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Ко всем клубам
          </Link>

          {/* Hero card */}
          <div className="relative mt-6 overflow-hidden rounded-2xl border border-steel-dim/20 bg-gradient-to-br from-petrol/70 via-ink-soft/80 to-ink/90 backdrop-blur">
            <div className="pointer-events-none absolute inset-0 -z-10"
              style={{
                background: 'radial-gradient(600px 300px at 30% 40%, rgba(201,162,39,0.06), transparent 70%)'
              }}
            />
            <div className="flex flex-col gap-8 p-6 sm:flex-row sm:items-start sm:p-8 lg:p-10">
              {/* Лого */}
              <div className="group relative flex-shrink-0">
                <div className="absolute -inset-1 rounded-2xl bg-gradient-to-br from-brass/30 to-rust/30 opacity-0 blur transition-opacity duration-500 group-hover:opacity-100" />
                <div className="relative flex h-40 w-40 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-brass/30 bg-ink sm:h-56 sm:w-56">
                  {c.logo_path ? (
                    <img
                      src={cloudinaryLogo(c.logo_path, 224) ?? c.logo_path}
                      alt=""
                      className="h-full w-full object-contain transition-transform duration-700 group-hover:scale-105"
                    />
                  ) : (
                    <span className="font-display text-3xl text-steel-dim sm:text-4xl">{initials(c.name)}</span>
                  )}
                </div>
              </div>

              {/* Инфо */}
              <div className="flex-1 pt-1">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <h1 className="min-w-0 flex-1 font-display text-3xl font-bold leading-tight text-bone sm:text-4xl lg:text-5xl">
                    {c.name}
                  </h1>
                  <span className="flex flex-shrink-0 flex-col items-end gap-1">
                    <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-rust/60">Рейтинг</span>
                    <span className="font-display text-3xl font-bold leading-none text-rust sm:text-4xl">{c.rating_points}</span>
                  </span>
                </div>

                {/* Город · основание · состав */}
                <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-sm text-steel">
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
                  <span className="inline-flex items-center gap-2">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-steel-dim">
                      <circle cx="7" cy="3.5" r="2" stroke="currentColor" strokeWidth="1.2"/>
                      <path d="M2 12.5c0-2.8 2.2-5 5-5s5 2.2 5 5" stroke="currentColor" strokeWidth="1.2"/>
                    </svg>
                    {c.coaches_count} тренеров
                  </span>
                </div>

                <div className="mt-3 flex items-center gap-2 font-mono text-sm text-steel-dim">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
                    <path d="M2 12V5.5L7 2l5 3.5V12H2z" stroke="currentColor" strokeWidth="1.2"/>
                    <path d="M5.5 12V8h3v4" stroke="currentColor" strokeWidth="1.2"/>
                  </svg>
                  Адрес: {c.address ?? 'отсутствует'}
                </div>

                <div className="mt-1.5 flex items-center gap-2 font-mono text-sm text-steel-dim">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
                    <path d="M2 2.5h3l1.5 4L5 7.5c.6 1.2 1.6 2.2 2.8 2.8l1-1.5 3.7 1.5v3c0 .9-.7 1.6-1.6 1.6C5.8 15 1 10.2 1 4.1 1 3.2 1.7 2.5 2.6 2.5" stroke="currentColor" strokeWidth="1.2"/>
                  </svg>
                  <span>Связаться:&nbsp;</span>
                  <span>{c.phone ?? 'не указан'}</span>
                </div>

                <div className="mt-1.5 flex items-center gap-2 font-mono text-sm text-steel-dim">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
                    <rect x="2" y="3" width="10" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                    <path d="M4.5 1.5V5M9.5 1.5V5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                    <path d="M2 6.5h10" stroke="currentColor" strokeWidth="1.2"/>
                  </svg>
                  Зарегистрировано: {formatDate(c.founded_date) || 'не указано'}
                </div>

                {c.description && (
                  <p className="mt-5 max-w-xl break-words whitespace-pre-line leading-relaxed text-steel">{c.description}</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Тело страницы */}
      <div className="mx-auto max-w-5xl px-5 py-10">
        <div className="grid gap-6 lg:grid-cols-2">
          <MemberList
            title="Спортсмены"
            subtitle="Члены клуба в реестре федерации"
            members={c.athletes}
            linkPrefix="/athletes"
            emptyMessage="Пока нет спортсменов"
          />
          <MemberList
            title="Тренеры"
            subtitle="Тренерский состав клуба"
            members={c.coaches}
            linkPrefix="/coaches"
            emptyMessage="Пока нет тренеров"
          />
        </div>

        {rating.data && rating.data.history.length > 0 && (
          <div className="mt-8">
            <RatingHistory items={rating.data.history} />
          </div>
        )}
      </div>
    </div>
  )
}
