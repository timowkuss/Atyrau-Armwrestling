import { Link } from 'react-router-dom'
import { useAthleteBirthdays } from '@/features/athletes/useAthletes'
import type { AthleteBirthdayItem } from '@/types/api'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { yearsWord } from '@/lib/age'

const DAY_LABELS = ['Сегодня', 'Завтра'] as const

function BirthdayRow({ athlete }: { athlete: AthleteBirthdayItem }) {
  const initials = athlete.full_name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
  return (
    <Link
      to={`/athletes/${athlete.id}`}
      className="group flex items-center gap-3 rounded-xl border border-steel-dim/15 bg-ink-soft/70 p-3 transition-all duration-300 hover:-translate-y-0.5 hover:border-brass/30 hover:shadow-[0_8px_28px_-10px_rgba(201,162,39,0.15)]"
    >
      <div className="relative flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border border-steel-dim/20 bg-ink font-display text-sm text-steel">
        {athlete.photo_path ? (
          <img
            src={cloudinaryThumb(athlete.photo_path, 48) ?? athlete.photo_path}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          initials
        )}
      </div>
      <div className="min-w-0">
        <p className="truncate font-display text-base font-semibold text-bone transition-colors group-hover:text-brass">
          {athlete.full_name}
        </p>
        <p className="font-mono text-sm text-steel-dim">
          {athlete.turns_age} {yearsWord(athlete.turns_age)}
        </p>
      </div>
    </Link>
  )
}

/** Блок «Дни рождения» — именинники на сегодня и завтра. Скрывается целиком,
 * если в базе ни у кого нет дня рождения в ближайшие два дня. */
export function BirthdaysBanner() {
  const { data, isLoading, isError } = useAthleteBirthdays()

  if (isLoading || isError || !data || data.length === 0) return null

  const today = data.filter((a) => a.day_offset === 0)
  const tomorrow = data.filter((a) => a.day_offset === 1)

  if (today.length === 0 && tomorrow.length === 0) return null

  return (
    <section className="mx-auto max-w-6xl px-5 pt-14">
      <div className="plate overflow-hidden rounded-[var(--radius-rivet)] p-6 sm:p-7">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-brass/25 bg-brass/10">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
              <rect x="1.5" y="4" width="15" height="12.5" rx="2" stroke="var(--color-brass)" strokeWidth="1.3" />
              <path d="M1.5 8h15" stroke="var(--color-brass)" strokeWidth="1.3" />
              <path d="M9 4V1.5" stroke="var(--color-brass)" strokeWidth="1.3" />
              <path d="M5.5 4V1.5M12.5 4V1.5" stroke="var(--color-brass)" strokeWidth="1.3" />
              <circle cx="5" cy="10.5" r="0.8" fill="var(--color-brass)" />
              <circle cx="9" cy="10.5" r="0.8" fill="var(--color-brass)" />
              <circle cx="13" cy="10.5" r="0.8" fill="var(--color-brass)" />
              <circle cx="5" cy="14" r="0.8" fill="var(--color-brass)" />
              <circle cx="9" cy="14" r="0.8" fill="var(--color-brass)" />
              <circle cx="13" cy="14" r="0.8" fill="var(--color-brass)" />
            </svg>
          </span>
          <div>
            <p className="text-eyebrow text-rust">Уведомления</p>
            <h2 className="font-display text-2xl text-bone">Дни рождения</h2>
          </div>
        </div>

        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          {today.length > 0 && (
            <div>
              <p className="text-eyebrow mb-3 text-steel">{DAY_LABELS[0]}</p>
              <div className="space-y-2.5">
                {today.map((a) => (
                  <BirthdayRow key={a.id} athlete={a} />
                ))}
              </div>
            </div>
          )}
          {tomorrow.length > 0 && (
            <div>
              <p className="text-eyebrow mb-3 text-steel">{DAY_LABELS[1]}</p>
              <div className="space-y-2.5">
                {tomorrow.map((a) => (
                  <BirthdayRow key={a.id} athlete={a} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
