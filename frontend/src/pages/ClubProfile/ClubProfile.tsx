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
    <div className="mx-auto max-w-5xl px-5 py-12">
      <Link to="/clubs" className="text-sm text-steel hover:text-brass">
        ← ко всем клубам
      </Link>

      <div className="plate mt-4 flex flex-col gap-6 rounded-[var(--radius-rivet)] p-6 sm:flex-row sm:items-center">
        <div className="flex h-32 w-32 flex-shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-rivet)] border-2 border-brass/50 bg-ink font-display text-2xl text-steel sm:h-36 sm:w-36">
          {c.logo_path ? (
            <img
              src={cloudinaryLogo(c.logo_path, 144) ?? c.logo_path}
              alt=""
              className="h-full w-full object-contain p-2"
              loading="lazy"
            />
          ) : (
            initials(c.name)
          )}
        </div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl text-bone sm:text-3xl">{c.name}</h1>
            <span className="text-eyebrow whitespace-nowrap rounded-[var(--radius-rivet)] border border-brass/40 px-2 py-1 text-brass">
              {c.rating_points} очк.
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-sm text-steel">
            {c.city_name && <span>{c.city_name}</span>}
            {formatDate(c.founded_date) && <span>осн. {formatDate(c.founded_date)}</span>}
            <span>{c.athletes_count} спортсменов</span>
            <span>{c.coaches_count} тренеров</span>
          </div>
          {c.address && <div className="mt-2 text-xs text-steel-dim">📍 {c.address}</div>}
        </div>
      </div>

      {c.description && (
        <div className="plate mt-6 rounded-[var(--radius-rivet)] p-6">
          <h2 className="text-eyebrow text-rust">О клубе</h2>
          <p className="mt-2 whitespace-pre-line text-steel">{c.description}</p>
        </div>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
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
  )
}
