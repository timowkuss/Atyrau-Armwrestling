import { Link, useParams } from 'react-router-dom'
import { useClub } from '@/features/clubs/useClubs'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import type { ClubMember } from '@/types/api'

function initials(name: string): string {
  return name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
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

export function ClubProfile() {
  const { id } = useParams<{ id: string }>()
  const clubId = Number(id)

  const club = useClub(clubId)

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
        <div className="flex h-24 w-24 flex-shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-rivet)] border-2 border-brass/50 bg-ink font-display text-2xl text-steel">
          {c.logo_path ? (
            <img
              src={cloudinaryThumb(c.logo_path, 96) ?? c.logo_path}
              alt=""
              className="h-full w-full object-cover"
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
            {c.founded_year && <span>с {c.founded_year}</span>}
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
    </div>
  )
}
