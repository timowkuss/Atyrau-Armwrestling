import { Link } from 'react-router-dom'
import type { CoachListItem } from '@/types/api'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { ageText } from '@/lib/age'

export function CoachCard({ coach }: { coach: CoachListItem }) {
  const at = ageText(coach.birth_date)
  return (
    <Link
      to={`/coaches/${coach.id}`}
      className="plate group flex flex-col rounded-[var(--radius-rivet)] p-5 transition-transform hover:-translate-y-0.5 hover:border-brass/50"
    >
      <div className="flex items-start justify-between">
        <div className="flex h-24 w-24 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-steel-dim bg-ink font-display text-xl text-steel sm:h-28 sm:w-28 sm:text-2xl">
          {coach.photo_path ? (
            <img
              src={cloudinaryThumb(coach.photo_path, 112) ?? coach.photo_path}
              alt=""
              className="h-full w-full object-cover"
              loading="lazy"
            />
          ) : (
            coach.full_name
              .split(' ')
              .map((p) => p[0])
              .slice(0, 2)
              .join('')
          )}
        </div>
        {coach.qualification && (
          <span className="text-eyebrow rounded-[var(--radius-rivet)] border border-brass/40 px-2 py-1 text-brass">
            {coach.qualification}
          </span>
        )}
      </div>
      <h3 className="mt-3 font-display text-lg leading-snug text-bone group-hover:text-brass">
        {coach.full_name}
      </h3>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-xs text-steel">
        {at !== null && <span>{at}</span>}
        {coach.city_name && <span>{coach.city_name}</span>}
        <span>{coach.athletes_count} спортсменов</span>
      </div>
      {coach.club_name && (
        <div className="mt-4 border-t border-steel-dim/30 pt-3 text-xs text-steel-dim">
          <div className="truncate">Клуб: {coach.club_name}</div>
        </div>
      )}
    </Link>
  )
}
