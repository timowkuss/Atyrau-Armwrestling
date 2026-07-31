import { Link } from 'react-router-dom'
import type { ClubListItem } from '@/types/api'
import { cloudinaryLogo } from '@/lib/cloudinaryImage'

function initials(name: string): string {
  return name
    .replace(/^(Спортивный|СК|Клуб|Центр|Федерация)\s+/i, '')
    .split(/[\s\-«»"']/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase()
}

export function ClubCard({ club }: { club: ClubListItem }) {
  return (
    <Link
      to={`/clubs/${club.id}`}
      className="plate group flex flex-col rounded-[var(--radius-rivet)] p-5 transition-transform hover:-translate-y-0.5 hover:border-brass/50"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-32 w-32 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-steel-dim bg-ink font-display text-xl text-steel sm:h-32 sm:w-32 sm:text-2xl">
          {club.logo_path ? (
            <img
              src={cloudinaryLogo(club.logo_path, 128) ?? club.logo_path}
              alt=""
              className="h-full w-full object-contain p-2"
              loading="lazy"
            />
          ) : (
            initials(club.name)
          )}
        </div>
        <span className="text-eyebrow whitespace-nowrap rounded-[var(--radius-rivet)] border border-brass/40 px-2 py-1 text-brass">
          {club.rating_points} очк.
        </span>
      </div>

      <h3 className="mt-3 font-display text-lg leading-snug text-bone group-hover:text-brass">
        {club.name}
      </h3>

      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-xs text-steel">
        {club.city_name && <span>{club.city_name}</span>}
        <span>{club.athletes_count} спортсменов</span>
      </div>

      {club.address && (
        <div className="mt-4 border-t border-steel-dim/30 pt-3 text-xs text-steel-dim">
          <div className="truncate">📍 {club.address}</div>
        </div>
      )}
    </Link>
  )
}
