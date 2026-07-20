import type { BracketMatchOut } from '@/types/api'

const BRACKET_LABEL: Record<string, string> = {
  winners: 'Верхняя сетка',
  losers: 'Нижняя сетка',
  final: 'Финал',
}

function groupBy<T, K extends string>(items: T[], key: (item: T) => K): Record<K, T[]> {
  return items.reduce(
    (acc, item) => {
      const k = key(item)
      ;(acc[k] ??= []).push(item)
      return acc
    },
    {} as Record<K, T[]>,
  )
}

function MatchRow({ match }: { match: BracketMatchOut }) {
  const isDone = match.status === 'done' || match.status === 'bye'
  const p1Won = isDone && match.winner_name != null && match.winner_name === match.p1_name
  const p2Won = isDone && match.winner_name != null && match.winner_name === match.p2_name

  return (
    <div className="flex flex-col gap-2.5 rounded-[var(--radius-rivet)] border border-steel-dim/20 bg-black/10 px-5 py-4 text-base">
      <div className="flex items-center justify-between gap-3">
        <p className={p1Won ? 'break-words font-medium text-brass' : 'break-words text-bone'}>
          {match.p1_name ?? '—'}
        </p>
        {isDone && p1Won && <span className="shrink-0 text-xs text-brass">Победа</span>}
      </div>
      <div className="h-px bg-steel-dim/15" />
      <div className="flex items-center justify-between gap-3">
        <p className={p2Won ? 'break-words font-medium text-brass' : 'break-words text-bone'}>
          {match.p2_name ?? '—'}
        </p>
        {isDone && p2Won && <span className="shrink-0 text-xs text-brass">Победа</span>}
      </div>
      <span className="self-end font-mono text-xs text-steel">
        {isDone ? 'Завершён' : 'Ожидание'}
      </span>
    </div>
  )
}

export function BracketBoard({ matches }: { matches: BracketMatchOut[] }) {
  if (matches.length === 0) return null

  const byCategory = groupBy(matches, (m) => m.category_name)

  return (
    <div className="space-y-10">
      {Object.entries(byCategory).map(([category, categoryMatches]) => {
        const byBracket = groupBy(categoryMatches, (m) => m.bracket)
        return (
          <div key={category}>
            <h3 className="font-display text-base text-brass">{category}</h3>
            <div className="mt-4 grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
              {Object.entries(byBracket).map(([bracket, bracketMatches]) => {
                const byRound = groupBy(bracketMatches, (m) => m.round_name ?? '—')
                return (
                  <div key={bracket} className="plate min-w-0 rounded-[var(--radius-rivet)] p-6">
                    <p className="text-eyebrow text-steel">{BRACKET_LABEL[bracket] ?? bracket}</p>
                    <div className="mt-5 space-y-6">
                      {Object.entries(byRound).map(([round, roundMatches]) => (
                        <div key={round}>
                          <p className="mb-3 font-mono text-xs text-steel">{round}</p>
                          <div className="space-y-3.5">
                            {roundMatches
                              .sort((a, b) => a.match_order - b.match_order)
                              .map((m) => (
                                <MatchRow key={m.id} match={m} />
                              ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
