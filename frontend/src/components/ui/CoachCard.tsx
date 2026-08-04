import { Link } from 'react-router-dom'
import type { CoachListItem } from '@/types/api'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { ageText } from '@/lib/age'

export function CoachCard({ coach }: { coach: CoachListItem }) {
  const at = ageText(coach.birth_date)
  return (
    <Link
      to={`/coaches/${coach.id}`}
      className="group relative block overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/70 p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brass/30 hover:shadow-[0_12px_40px_-8px_rgba(201,162,39,0.12)]"
    >
      <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-brass/5 blur-3xl transition-all duration-500 group-hover:bg-brass/10" />
      <div className="flex items-start gap-4">
        <div className="relative flex h-28 w-28 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-steel-dim/20 bg-ink font-display text-2xl text-steel transition-all duration-300 group-hover:border-brass/30 sm:h-32 sm:w-32 sm:text-3xl">
          {coach.photo_path ? (
            <img
              src={cloudinaryThumb(coach.photo_path, 128) ?? coach.photo_path}
              alt=""
              className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
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

        <div className="min-w-0 flex-1">
          {/* Имя + квалификация */}
          <div className="flex items-start justify-between gap-2">
            <h3 className="truncate font-display text-xl font-semibold leading-snug text-bone transition-colors group-hover:text-brass">
              {coach.full_name}
            </h3>
            {coach.qualification && (
              <span className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-full border border-brass/20 bg-brass/5 px-3 py-1 font-mono text-[11px] font-medium tracking-wider text-brass/80">
                <span className="h-1.5 w-1.5 rounded-full bg-brass/40" />
                {coach.qualification}
              </span>
            )}
          </div>

          {/* Возраст · город */}
          <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-sm text-steel-dim">
            {at !== null && <span>{at}</span>}
            {at !== null && coach.city_name && <span>·</span>}
            {coach.city_name && <span>{coach.city_name}</span>}
          </div>

          {/* Подопечные спортсмены */}
          <div className="mt-2 flex items-center gap-1.5 font-mono text-sm text-steel-dim">
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
              <circle cx="7" cy="5" r="2.6" stroke="currentColor" strokeWidth="1.2" />
              <path d="M2 12.5c0-2.8 2.2-5 5-5s5 2.2 5 5" stroke="currentColor" strokeWidth="1.2" />
            </svg>
            <span>{coach.athletes_count} спортсменов</span>
          </div>

          {/* Клуб */}
          {coach.club_name && (
            <div className="mt-3 flex items-center gap-1.5 truncate border-t border-steel-dim/15 pt-3 text-sm text-steel-dim">
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
                <path d="M2 12V5.5L7 2l5 3.5V12H2z" stroke="currentColor" strokeWidth="1.2" />
                <path d="M5.5 12V8h3v4" stroke="currentColor" strokeWidth="1.2" />
              </svg>
              <span className="truncate">{coach.club_name}</span>
            </div>
          )}
        </div>
      </div>
    </Link>
  )
}
