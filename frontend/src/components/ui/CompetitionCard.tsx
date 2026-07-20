import { Link } from 'react-router-dom'
import type { CompetitionListItem } from '@/types/api'

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })
}

export function CompetitionCard({ competition }: { competition: CompetitionListItem }) {
  const upcoming = new Date(competition.date).getTime() > Date.now()
  return (
    <Link
      to={`/competitions/${competition.id}`}
      className="plate group flex flex-col justify-between rounded-[var(--radius-rivet)] p-6 transition-transform hover:-translate-y-0.5 hover:border-brass/50"
    >
      <div>
        <div className="flex items-center justify-between">
          <span className="text-eyebrow text-rust">{formatDate(competition.date)}</span>
          {upcoming && (
            <span className="text-eyebrow rounded-[var(--radius-rivet)] bg-brass/15 px-2 py-0.5 text-brass">
              скоро
            </span>
          )}
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
