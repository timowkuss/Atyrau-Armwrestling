import { Link } from 'react-router-dom'
import type { CompetitionListItem, CompetitionStatus } from '@/types/api'

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })
}

function statusBadge(status: CompetitionStatus) {
  const map: Record<CompetitionStatus, { label: string; cls: string }> = {
    draft:        { label: 'черновик',  cls: 'bg-steel-dim/30 text-steel-dim' },
    published:    { label: 'скоро',     cls: 'bg-brass/15 text-brass' },
    in_progress:  { label: 'идёт',     cls: 'bg-emerald-500/20 text-emerald-400' },
    completed:    { label: 'завершён',  cls: 'bg-rust/15 text-rust' },
  }
  const b = map[status]
  return (
    <span className={`text-eyebrow rounded-[var(--radius-rivet)] px-2 py-0.5 ${b.cls}`}>
      {b.label}
    </span>
  )
}

export function CompetitionCard({ competition }: { competition: CompetitionListItem }) {
  return (
    <Link
      to={`/competitions/${competition.id}`}
      className="plate group flex flex-col justify-between rounded-[var(--radius-rivet)] p-6 transition-transform hover:-translate-y-0.5 hover:border-brass/50"
    >
      <div>
        <div className="flex items-center justify-between">
          <span className="text-eyebrow text-rust">{formatDate(competition.date)}</span>
          {statusBadge(competition.status)}
        </div>
        <h3 className="mt-2.5 font-display text-xl leading-snug text-bone group-hover:text-brass">
          {competition.name}
        </h3>
        {competition.location_city_name && (
          <p className="mt-1 text-sm text-steel">{competition.location_city_name}</p>
        )}
      </div>
      <div className="mt-5 flex items-center justify-between border-t border-steel-dim/30 pt-3 font-mono text-xs text-steel-dim">
        <span>{competition.organizer ?? 'Федерация армрестлинга Атырау'}</span>
        <span>{competition.participants_count} участников</span>
      </div>
    </Link>
  )
}
