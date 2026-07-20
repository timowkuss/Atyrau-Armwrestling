import { Link } from 'react-router-dom'
import type { AthleteListItem } from '@/types/api'

function age(birthDate: string | null): number | null {
  if (!birthDate) return null
  const b = new Date(birthDate)
  const diff = Date.now() - b.getTime()
  return Math.floor(diff / (365.25 * 24 * 60 * 60 * 1000))
}

export function AthleteCard({ athlete }: { athlete: AthleteListItem }) {
  const a = age(athlete.birth_date)
  return (
    <Link
      to={`/athletes/${athlete.id}`}
      className="plate group flex flex-col rounded-[var(--radius-rivet)] p-5 transition-transform hover:-translate-y-0.5 hover:border-brass/50"
    >
      <div className="flex items-start justify-between">
        <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-full border border-steel-dim bg-ink font-display text-lg text-steel">
          {athlete.photo_path ? (
            <img src={athlete.photo_path} alt="" className="h-full w-full object-cover" />
          ) : (
            athlete.full_name
              .split(' ')
              .map((p) => p[0])
              .slice(0, 2)
              .join('')
          )}
        </div>
        {athlete.rank && (
          <span className="text-eyebrow rounded-[var(--radius-rivet)] border border-brass/40 px-2 py-1 text-brass">
            {athlete.rank}
          </span>
        )}
      </div>
      <h3 className="mt-3 font-display text-lg leading-snug text-bone group-hover:text-brass">
        {athlete.full_name}
      </h3>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-xs text-steel">
        {a !== null && <span>{a} лет</span>}
        <span>{athlete.gender === 'male' ? 'муж' : 'жен'}</span>
        {athlete.city_name && <span>{athlete.city_name}</span>}
      </div>
      {(athlete.club_name || athlete.coach_name) && (
        <div className="mt-4 border-t border-steel-dim/30 pt-3 text-xs text-steel-dim">
          {athlete.club_name && <div className="truncate">Клуб: {athlete.club_name}</div>}
          {athlete.coach_name && <div className="truncate">Тренер: {athlete.coach_name}</div>}
        </div>
      )}
    </Link>
  )
}
