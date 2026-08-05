import { Link } from 'react-router-dom'
import { useAthleteBirthdays } from '@/features/athletes/useAthletes'
import type { AthleteBirthdayItem } from '@/types/api'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { yearsWord } from '@/lib/age'

const DAY_LABELS = ['Сегодня', 'Завтра'] as const

function BirthdayChip({ athlete }: { athlete: AthleteBirthdayItem }) {
  const initials = athlete.full_name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
  return (
    <Link
      to={`/athletes/${athlete.id}`}
      className="group flex items-center gap-2.5 rounded-full border border-steel-dim/15 bg-ink-soft/70 py-1.5 pl-1.5 pr-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-brass/30 hover:bg-ink-soft hover:shadow-[0_10px_30px_-12px_rgba(201,162,39,0.35)]"
    >
      <span className="relative flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border border-steel-dim/25 bg-ink font-display text-[0.65rem] font-semibold text-steel">
        {athlete.photo_path ? (
          <img
            src={cloudinaryThumb(athlete.photo_path, 40) ?? athlete.photo_path}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          initials
        )}
      </span>
      <span className="flex flex-col leading-none">
        <span className="max-w-[9rem] truncate font-display text-sm font-semibold text-bone transition-colors group-hover:text-brass">
          {athlete.full_name}
        </span>
        <span className="mt-1 font-mono text-[0.7rem] text-steel-dim">
          {athlete.turns_age} {yearsWord(athlete.turns_age)}
        </span>
      </span>
    </Link>
  )
}

/** Уведомление о днях рождения — прозрачная «стеклянная» лента под шапкой.
 * Скрывается целиком, если в базе ни у кого нет дня рождения в ближайшие два дня. */
export function BirthdaysBanner() {
  const { data, isLoading, isError } = useAthleteBirthdays()

  if (isLoading || isError || !data || data.length === 0) return null

  const today = data.filter((a) => a.day_offset === 0)
  const tomorrow = data.filter((a) => a.day_offset === 1)

  if (today.length === 0 && tomorrow.length === 0) return null

  const groups = [
    { label: DAY_LABELS[0], items: today },
    { label: DAY_LABELS[1], items: tomorrow },
  ].filter((g) => g.items.length > 0)

  return (
    <section className="relative z-10 mx-auto max-w-6xl px-5 pt-5 sm:pt-7" aria-label="Дни рождения">
      <div className="relative overflow-hidden rounded-2xl border border-steel-dim/15 bg-ink/25 px-4 py-4 backdrop-blur-xl sm:px-6 sm:py-5">
        {/* Мягкие внутренние свечения — латунь и каспийская вода */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 -top-28 h-60 w-60 rounded-full bg-brass/10 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 -right-20 h-60 w-60 rounded-full bg-petrol-2/20 blur-3xl"
        />
        {/* Тонкая верхняя «засветка» стекла */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-bone/25 to-transparent"
        />

        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:gap-7">
          <div className="flex items-center gap-3.5">
            <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-brass/25 bg-brass/10 shadow-[0_0_24px_-6px_rgba(201,162,39,0.5)]">
              <svg width="19" height="19" viewBox="0 0 18 18" fill="none" aria-hidden="true">
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
              <h2 className="font-display text-lg font-semibold leading-tight text-bone">Дни рождения</h2>
            </div>
          </div>

          <div aria-hidden="true" className="hidden h-10 w-px shrink-0 bg-steel-dim/25 lg:block" />

          <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
            {groups.map((group) => (
              <div key={group.label} className="flex flex-wrap items-center gap-2.5">
                <span className="text-eyebrow text-steel-dim">{group.label}</span>
                {group.items.map((a) => (
                  <BirthdayChip key={a.id} athlete={a} />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
