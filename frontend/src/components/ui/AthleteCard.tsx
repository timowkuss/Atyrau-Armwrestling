import { Link } from 'react-router-dom'
import type { AthleteListItem } from '@/types/api'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { ageText } from '@/lib/age'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function AthleteCard({ athlete }: { athlete: AthleteListItem }) {
  const at = ageText(athlete.birth_date)
  return (
    <Link
      to={`/athletes/${athlete.id}`}
      className="group relative overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/70 p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brass/30 hover:shadow-[0_12px_40px_-8px_rgba(201,162,39,0.12)]"
    >
      <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-brass/5 blur-3xl transition-all duration-500 group-hover:bg-brass/10" />
      <div className="flex items-start justify-between">
        <div className="relative flex h-28 w-28 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-steel-dim/20 bg-ink font-display text-2xl text-steel transition-all duration-300 group-hover:border-brass/30 sm:h-32 sm:w-32 sm:text-3xl">
          {athlete.photo_path ? (
            <img
              src={cloudinaryThumb(athlete.photo_path, 128) ?? athlete.photo_path}
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
        <div className="flex flex-col items-end gap-2">
          {athlete.rank && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brass/20 bg-brass/5 px-3 py-1 font-mono text-[11px] font-medium tracking-wider text-brass/80">
              <span className="h-1.5 w-1.5 rounded-full bg-brass/40" />
              {athlete.rank}
            </span>
          )}
          <div className="flex flex-col items-end">
            <span className="font-mono text-[10px] font-medium uppercase tracking-wider text-rust/60">Rating</span>
            <span className="font-display text-2xl font-bold leading-none text-rust">{athlete.elo_combined}</span>
          </div>
        </div>
      </div>
      <h3 className="mt-5 font-display text-xl font-semibold leading-snug text-bone transition-colors group-hover:text-brass">
        {athlete.full_name}
      </h3>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-sm text-steel-dim">
        {athlete.birth_date && (
          <span className="flex items-center gap-1">
            <svg width="11" height="11" viewBox="0 0 14 14" fill="none">
              <rect x="2" y="3" width="10" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
              <path d="M4.5 1.5V5M9.5 1.5V5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
              <path d="M2 6.5h10" stroke="currentColor" strokeWidth="1.2"/>
            </svg>
            {formatDate(athlete.birth_date)}
          </span>
        )}
        {at !== null && <span>{at}</span>}
        <span className="flex items-center gap-1">
          <span className={`h-2 w-2 rounded-full ${athlete.gender === 'male' ? 'bg-rust/60' : 'bg-brass/60'}`} />
          {athlete.gender === 'male' ? 'муж' : 'жен'}
        </span>
        {athlete.city_name && (
          <span className="flex items-center gap-1">
            <svg width="11" height="11" viewBox="0 0 10 10" fill="none">
              <path d="M5 1C3.06 1 1.5 2.56 1.5 4.5c0 2.62 3.5 5 3.5 5s3.5-2.38 3.5-5C8.5 2.56 6.94 1 5 1zm0 5a1.5 1.5 0 110-3 1.5 1.5 0 010 3z" fill="currentColor" opacity="0.5"/>
            </svg>
            {athlete.city_name}
          </span>
        )}
      </div>
      {(athlete.club_name || athlete.coach_name) && (
        <div className="mt-4 border-t border-steel-dim/15 pt-3 text-sm text-steel-dim">
          {athlete.club_name && <div className="flex items-center gap-1.5 truncate"><svg width="11" height="11" viewBox="0 0 10 10" fill="none"><path d="M1 8V4l4-2.5L9 4v4z" stroke="currentColor" strokeWidth="1.2"/></svg>{athlete.club_name}</div>}
          {athlete.coach_name && <div className="mt-1 flex items-center gap-1.5 truncate"><svg width="11" height="11" viewBox="0 0 10 10" fill="none"><circle cx="5" cy="3.5" r="2" stroke="currentColor" strokeWidth="1.2"/><path d="M1.5 9c0-2.2 1.8-4 3.5-4s3.5 1.8 3.5 4" stroke="currentColor" strokeWidth="1.2"/></svg>{athlete.coach_name}</div>}
        </div>
      )}
    </Link>
  )
}
