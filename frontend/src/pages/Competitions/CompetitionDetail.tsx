import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { useCompetition, useCompetitionBracket, useCompetitionParticipants, useCompetitionResults } from '@/features/competitions/useCompetitions'
import { api } from '@/lib/api'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { MedalBadge } from '@/components/ui/Medal'
import { BracketBoard } from '@/components/ui/BracketBoard'
import type { CompetitionStatus, ParticipantOut } from '@/types/api'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })
}

function formatLabel(c: {
  format_type: 'combined' | 'separate' | null
  bracket_system: 'double' | 'single' | null
  weight_tolerance: number | null
}) {
  const parts: string[] = []
  if (c.format_type) {
    parts.push(c.format_type === 'combined' ? 'Двоеборье' : 'По одной руке')
  }
  if (c.bracket_system) {
    parts.push(c.bracket_system === 'single' ? 'До одного поражения' : 'До двух поражений')
  }
  if (c.weight_tolerance != null) {
    parts.push(`Допуск по весу ${c.weight_tolerance} кг`)
  }
  return parts
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
    <span className={`text-eyebrow rounded-[var(--radius-rivet)] px-2.5 py-0.5 ${b.cls}`}>
      {b.label}
    </span>
  )
}

function ParticipantList({ participants }: { participants: ParticipantOut[] }) {
  if (participants.length === 0) return null

  const byCategory = participants.reduce<Record<string, ParticipantOut[]>>((acc, p) => {
    ;(acc[p.category_name] ??= []).push(p)
    return acc
  }, {})

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {Object.entries(byCategory).map(([category, members]) => (
        <div key={category} className="plate rounded-[var(--radius-rivet)] p-5">
          <div className="flex items-center justify-between">
            <h3 className="font-display text-sm text-brass">{category}</h3>
            <span className="text-eyebrow text-steel">{members.length}</span>
          </div>
          <ol className="mt-3 space-y-1.5">
            {members.map((m, i) => (
              <li key={m.athlete_id} className="flex items-baseline gap-2 text-sm">
                <span className="shrink-0 w-5 text-right font-mono text-steel-dim">{i + 1}.</span>
                <Link to={`/athletes/${m.athlete_id}`} className="truncate text-bone hover:text-brass">
                  {m.athlete_name}
                </Link>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}

export function CompetitionDetail() {
  const { id } = useParams<{ id: string }>()
  const competitionId = Number(id)

  const competition = useCompetition(competitionId)
  const results = useCompetitionResults(competitionId)
  const participants = useCompetitionParticipants(competitionId)
  const bracket = useCompetitionBracket(competitionId)
  const photos = useQuery({
    queryKey: ['competition', competitionId, 'photos'],
    queryFn: () => api.competitions.photos(competitionId),
    enabled: Number.isFinite(competitionId),
  })

  if (competition.isLoading) return <LoadingState label="Загрузка турнира" />
  if (competition.isError) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <ErrorState
          title="Турнир не найден"
          message={(competition.error as Error).message}
          onRetry={() => competition.refetch()}
        />
      </div>
    )
  }
  if (!competition.data) return null

  const c = competition.data
  const isFinished = c.status === 'completed'
  const isLive = c.status === 'in_progress'
  const resultsByCategory = (results.data ?? []).reduce<Record<string, typeof results.data>>((acc, r) => {
    ;(acc[r.category_name] ??= []).push(r)
    return acc
  }, {})

  return (
    <div className="mx-auto max-w-4xl px-5 py-12">
      <Link to="/competitions" className="text-sm text-steel hover:text-brass">
        ← ко всем турнирам
      </Link>

      <div className="plate mt-4 rounded-[var(--radius-rivet)] p-6">
        <div className="flex items-center justify-between">
          <p className="text-eyebrow text-rust">{formatDate(c.date)}</p>
          <div className="flex items-center gap-3">
            {statusBadge(c.status)}
            {isLive && (
              <a
                href={`/competitions/${competitionId}/board`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-eyebrow rounded-[var(--radius-rivet)] border border-brass/40 bg-brass/10 px-3 py-1.5 text-brass hover:bg-brass/20"
              >
                📺 Табло
              </a>
            )}
          </div>
        </div>
        <h1 className="mt-2 font-display text-2xl text-bone sm:text-3xl">{c.name}</h1>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-sm text-steel">
          {c.location_city_name && <span>{c.location_city_name}</span>}
          <span>{c.organizer ?? 'Федерация армрестлинга Атырау'}</span>
          <span>{c.participants_count} участников</span>
        </div>
        {formatLabel(c).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-steel-dim">
            {formatLabel(c).map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
        )}
        {c.description && <p className="mt-4 max-w-2xl text-sm text-steel">{c.description}</p>}
        {c.categories.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {c.categories.map((cat) => (
              <span
                key={cat.id}
                className="text-eyebrow rounded-[var(--radius-rivet)] border border-steel-dim px-2 py-1 text-steel"
              >
                {cat.name} · {cat.hand === 'left' ? 'левая' : 'правая'}
              </span>
            ))}
          </div>
        )}
      </div>

      {photos.data && photos.data.length > 0 && (
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {photos.data.map((p) => (
            <img key={p.id} src={p.url} alt={p.caption ?? ''} className="aspect-square rounded-[var(--radius-rivet)] object-cover" />
          ))}
        </div>
      )}

      {participants.data && participants.data.length > 0 && (
        <section className="mt-10">
          <h2 className="font-display text-xl text-bone">Участники</h2>
          <div className="rivet-line my-4" />
          <ParticipantList participants={participants.data} />
        </section>
      )}

      {isFinished && bracket.data && bracket.data.length > 0 && (
        <section className="mt-10 mb-16">
          <h2 className="font-display text-xl text-bone">Турнирная сетка</h2>
          <div className="rivet-line my-4" />
          <BracketBoard matches={bracket.data} />
        </section>
      )}

      <section className={`mt-10 ${isFinished && bracket.data && bracket.data.length > 0 ? '' : 'mb-16'}`}>
        <h2 className="font-display text-xl text-bone">Результаты</h2>
        <div className="rivet-line my-4" />
        {results.isLoading && <LoadingState label="Загрузка результатов" />}
        {results.isError && (
          <ErrorState message={(results.error as Error).message} onRetry={() => results.refetch()} />
        )}
        {results.data && results.data.length === 0 && (
          <EmptyState title={isFinished ? 'Результаты не найдены' : 'Результаты ещё не внесены'} />
        )}
        {Object.entries(resultsByCategory).map(([category, rows]) => (
          <div key={category} className="mb-6">
            <h3 className="font-display text-sm text-brass">{category}</h3>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full min-w-[420px] border-collapse text-left text-sm">
                <tbody>
                  {rows?.map((r, i) => (
                    <tr key={i} className="border-b border-steel-dim/15">
                      <td className="py-2 pr-4 font-mono text-bone">{r.place ?? '—'}</td>
                      <td className="py-2 pr-4">
                        <Link to={`/athletes/${r.athlete_id}`} className="text-bone hover:text-brass">
                          {r.athlete_name}
                        </Link>
                      </td>
                      <td className="py-2 pr-4 text-steel">{r.club_name ?? '—'}</td>
                      <td className="py-2">
                        <MedalBadge medal={r.medal} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </section>
    </div>
  )
}
