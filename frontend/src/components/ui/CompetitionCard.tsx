import { Link } from 'react-router-dom'
import type { CompetitionListItem, CompetitionStatus } from '@/types/api'

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })
}

function statusBadge(status: CompetitionStatus) {
  const map: Record<CompetitionStatus, { label: string; dot: string; text: string }> = {
    draft:        { label: 'черновик', dot: 'bg-steel-dim/50', text: 'text-steel-dim' },
    published:    { label: 'скоро',    dot: 'bg-brass/60',     text: 'text-brass/80' },
    in_progress:  { label: 'идёт',     dot: 'bg-success',      text: 'text-success' },
    completed:    { label: 'завершён', dot: 'bg-rust/70',      text: 'text-rust' },
  }
  const b = map[status]
  return (
    <span className={`inline-flex flex-shrink-0 items-center gap-1.5 rounded-full border border-brass/20 bg-brass/5 px-3 py-1 font-mono text-[11px] font-medium tracking-wider ${b.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${b.dot}`} />
      {b.label}
    </span>
  )
}

export function CompetitionCard({ competition }: { competition: CompetitionListItem }) {
  return (
    <Link
      to={`/competitions/${competition.id}`}
      className="group relative flex flex-col overflow-hidden rounded-xl border border-steel-dim/15 bg-gradient-to-br from-petrol/40 to-ink-soft/70 p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brass/30 hover:shadow-[0_12px_40px_-8px_rgba(201,162,39,0.12)]"
    >
      <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-brass/5 blur-3xl transition-all duration-500 group-hover:bg-brass/10" />

      <div className="flex flex-1 flex-col">
        <div className="flex items-start justify-between gap-2">
          <span className="font-mono text-[11px] font-medium uppercase tracking-wider text-rust/80">
            {formatDate(competition.date)}
          </span>
          {statusBadge(competition.status)}
        </div>

        <h3 className="mt-3 font-display text-xl font-semibold leading-snug text-bone transition-colors group-hover:text-brass">
          {competition.name}
        </h3>

        {competition.location_city_name && (
          <p className="mt-1.5 flex items-center gap-1 text-sm text-steel-dim">
            <svg width="11" height="11" viewBox="0 0 10 10" fill="none" className="flex-shrink-0">
              <path d="M5 1C3.06 1 1.5 2.56 1.5 4.5c0 2.62 3.5 5 3.5 5s3.5-2.38 3.5-5C8.5 2.56 6.94 1 5 1zm0 5a1.5 1.5 0 110-3 1.5 1.5 0 010 3z" fill="currentColor" opacity="0.5"/>
            </svg>
            {competition.location_city_name}
          </p>
        )}
      </div>

      <div className="mt-5 flex items-center justify-between gap-2 border-t border-steel-dim/15 pt-3 font-mono text-xs text-steel-dim">
        <span className="truncate">{competition.organizer ?? 'Федерация армрестлинга Атырау'}</span>
        <span className="flex flex-shrink-0 items-center gap-1">
          <svg width="11" height="11" viewBox="0 0 14 14" fill="none">
            <circle cx="7" cy="5" r="2.6" stroke="currentColor" strokeWidth="1.2"/>
            <path d="M2 12.5c0-2.8 2.2-5 5-5s5 2.2 5 5" stroke="currentColor" strokeWidth="1.2"/>
          </svg>
          {competition.participants_count}
        </span>
      </div>
    </Link>
  )
}
