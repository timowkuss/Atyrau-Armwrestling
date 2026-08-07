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
      className="group relative block overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/70 p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brass/30 hover:shadow-[0_12px_40px_-8px_rgba(201,162,39,0.12)]"
    >
      <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-brass/5 blur-3xl transition-all duration-500 group-hover:bg-brass/10" />
      <div className="flex items-start justify-between">
        <div className="relative flex h-28 w-28 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-steel-dim/20 bg-ink font-display text-2xl text-steel transition-all duration-300 group-hover:border-brass/30 sm:h-32 sm:w-32 sm:text-3xl">
          {club.logo_path ? (
            <img
              src={cloudinaryLogo(club.logo_path, 128) ?? club.logo_path}
              alt=""
              className="h-full w-full object-contain transition-transform duration-500 group-hover:scale-105"
              loading="lazy"
            />
          ) : (
            initials(club.name)
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex flex-col items-end">
            <span className="font-mono text-[10px] font-medium uppercase tracking-wider text-rust/60">Рейтинг</span>
            <span className="font-display text-2xl font-bold leading-none text-rust">{club.rating_points}</span>
          </div>
        </div>
      </div>

      <h3 className="mt-5 font-display text-xl font-semibold leading-snug text-bone transition-colors group-hover:text-brass">
        {club.name}
      </h3>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-sm text-steel-dim">
        {club.city_name && (
          <span className="flex items-center gap-1">
            <svg width="11" height="11" viewBox="0 0 10 10" fill="none">
              <path d="M5 1C3.06 1 1.5 2.56 1.5 4.5c0 2.62 3.5 5 3.5 5s3.5-2.38 3.5-5C8.5 2.56 6.94 1 5 1zm0 5a1.5 1.5 0 110-3 1.5 1.5 0 010 3z" fill="currentColor" opacity="0.5"/>
            </svg>
            {club.city_name}
          </span>
        )}
      </div>

      <div className="mt-1.5 flex items-center gap-1.5 truncate font-mono text-xs text-steel-dim/80">
        <svg width="11" height="11" viewBox="0 0 14 14" fill="none" className="flex-shrink-0">
          <path d="M2 12V5.5L7 2l5 3.5V12H2z" stroke="currentColor" strokeWidth="1.2" />
          <path d="M5.5 12V8h3v4" stroke="currentColor" strokeWidth="1.2" />
        </svg>
        <span className="truncate">Адрес: {club.address ?? 'отсутствует'}</span>
      </div>

      <div className="mt-5 grid grid-cols-2 divide-x divide-steel-dim/15 border-t border-steel-dim/15 pt-4">
        <div className="flex items-center gap-3 pr-4">
          <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-petrol-2/50 text-steel transition-colors group-hover:bg-petrol-2/70">
            <svg width="16" height="16" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="5" r="2.6" stroke="currentColor" strokeWidth="1.2"/>
              <path d="M2 12.5c0-2.8 2.2-5 5-5s5 2.2 5 5" stroke="currentColor" strokeWidth="1.2"/>
            </svg>
          </span>
          <span>
            <span className="block font-display text-xl font-bold leading-none text-bone">{club.athletes_count}</span>
            <span className="mt-1 block font-mono text-[10px] font-medium uppercase tracking-wider text-steel-dim">спортсмены</span>
          </span>
        </div>
        <div className="flex items-center gap-3 pl-4">
          <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-petrol-2/50 text-steel transition-colors group-hover:bg-petrol-2/70">
            <svg width="16" height="16" viewBox="0 0 14 14" fill="none">
              <path d="M7 8.5c2.2 0 4 1.8 4 4" stroke="currentColor" strokeWidth="1.2"/>
              <path d="M7 8.5c-2.2 0-4 1.8-4 4" stroke="currentColor" strokeWidth="1.2"/>
              <path d="M7 5.5v3" stroke="currentColor" strokeWidth="1.2"/>
              <circle cx="7" cy="3.2" r="2" stroke="currentColor" strokeWidth="1.2"/>
            </svg>
          </span>
          <span>
            <span className="block font-display text-xl font-bold leading-none text-bone">{club.coaches_count}</span>
            <span className="mt-1 block font-mono text-[10px] font-medium uppercase tracking-wider text-steel-dim">тренеры</span>
          </span>
        </div>
      </div>
    </Link>
  )
}
