import { Link } from 'react-router-dom'
import type { AthleteListItem } from '@/types/api'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { age } from '@/lib/age'

function birthYear(birthDate: string | null): number | null {
  if (!birthDate) return null
  const y = new Date(birthDate).getFullYear()
  return Number.isNaN(y) ? null : y
}

export function AthleteCard({ athlete }: { athlete: AthleteListItem }) {
  const a = age(athlete.birth_date)
  const year = birthYear(athlete.birth_date)
  return (
    <Link
      to={`/athletes/${athlete.id}`}
      className="group relative block overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/70 p-5 transition-all duration-300 hover:-translate-y-1 hover:border-brass/30 hover:shadow-[0_12px_40px_-8px_rgba(201,162,39,0.12)]"
    >
      <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-brass/5 blur-3xl transition-all duration-500 group-hover:bg-brass/10" />
      <div className="flex items-start gap-4">
        <div className="relative flex h-20 w-20 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-steel-dim/20 bg-ink font-display text-xl text-steel transition-all duration-300 group-hover:border-brass/30 sm:h-24 sm:w-24 sm:text-2xl">
          {athlete.photo_path ? (
            <img
              src={cloudinaryThumb(athlete.photo_path, 96) ?? athlete.photo_path}
              alt=""
              className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
              loading="lazy"
            />
          ) : (
            athlete.full_name
              .split(' ')
              .map((p) => p[0])
              .slice(0, 2)
              .join('')
          )}
        </div>

        <div className="min-w-0 flex-1">
          {/* Имя + разряд */}
          <div className="flex items-start justify-between gap-2">
            <h3 className="truncate font-display text-lg font-semibold leading-snug text-bone transition-colors group-hover:text-brass">
              {athlete.full_name}
            </h3>
            {athlete.rank && (
              <span className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-full border border-brass/20 bg-brass/5 px-2.5 py-1 font-mono text-[10px] font-medium tracking-wider text-brass/80">
                <span className="h-1.5 w-1.5 rounded-full bg-brass/40" />
                {athlete.rank}
              </span>
            )}
          </div>

          {/* Пол · город                рейтинг */}
          <div className="mt-2 flex items-center justify-between gap-2 font-mono text-xs text-steel-dim">
            <span className="flex min-w-0 items-center gap-1.5">
              <span className={`h-2 w-2 flex-shrink-0 rounded-full ${athlete.gender === 'male' ? 'bg-rust/60' : 'bg-brass/60'}`} />
              <span className="truncate">
                {athlete.gender === 'male' ? 'мужчины' : 'женщины'}
                {athlete.city_name && <span> · {athlete.city_name}</span>}
              </span>
            </span>
            <span className="flex flex-shrink-0 items-baseline gap-1.5">
              <span className="font-mono text-[10px] font-medium uppercase tracking-wider text-rust/60">Rating</span>
              <span className="font-display text-lg font-bold leading-none text-rust">{athlete.elo_combined}</span>
            </span>
          </div>

          {/* Год рождения · возраст */}
          <div className="mt-1.5 flex items-center gap-1.5 font-mono text-xs text-steel-dim">
            {(year !== null || a !== null) && (
              <span className="inline-flex items-center gap-1.5">
                <svg width="11" height="11" viewBox="0 0 14 14" fill="none" className="text-steel-dim">
                  <rect x="2" y="3" width="10" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                  <path d="M4.5 1.5V5M9.5 1.5V5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                  <path d="M2 6.5h10" stroke="currentColor" strokeWidth="1.2"/>
                </svg>
                {year !== null && <span>{year} г.</span>}
                {year !== null && a !== null && <span>·</span>}
                {a !== null && <span>{a} лет</span>}
              </span>
            )}
          </div>

          {/* Тренер · клуб */}
          {(athlete.coach_name || athlete.club_name) && (
            <div className="mt-2 border-t border-steel-dim/15 pt-2 text-xs text-steel-dim">
              {athlete.coach_name && (
                <div className="flex items-center gap-1.5 truncate">
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <circle cx="5" cy="3.5" r="2" stroke="currentColor" strokeWidth="1.2" />
                    <path d="M1.5 9c0-2.2 1.8-4 3.5-4s3.5 1.8 3.5 4" stroke="currentColor" strokeWidth="1.2" />
                  </svg>
                  <span className="truncate">Тренер: {athlete.coach_name}</span>
                </div>
              )}
              {athlete.club_name && (
                <div className="mt-0.5 flex items-center gap-1.5 truncate">
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M1 8V4l4-2.5L9 4v4z" stroke="currentColor" strokeWidth="1.2" />
                  </svg>
                  <span className="truncate">Клуб: {athlete.club_name}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Link>
  )
}
