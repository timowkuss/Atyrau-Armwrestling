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
    <div className="flex items-center justify-between gap-3 rounded-[var(--radius-rivet)] border border-steel-dim/20 bg-black/10 px-3 py-2 text-sm">
      <div className="min-w-0 flex-1">
        <p className={p1Won ? 'truncate text-brass' : 'truncate text-bone'}>{match.p1_name ?? '—'}</p>
        <p className={p2Won ? 'truncate text-brass' : 'truncate text-bone'}>{match.p2_name ?? '—'}</p>
      </div>
      <span className="shrink-0 font-mono text-xs text-steel">
        {isDone ? 'Завершён' : 'Ожидание'}
      </span>
    </div>
  )
}

export function BracketBoard({ matches }: { matches: BracketMatchOut[] }) {
  if (matches.length === 0) return null

  const byCategory = groupBy(matches, (m) => m.category_name)

  return (
    <div className="space-y-8">
      {Object.entries(byCategory).map(([category, categoryMatches]) => {
        const byBracket = groupBy(categoryMatches, (m) => m.bracket)
        return (
          <div key={category}>
            <h3 className="font-display text-sm text-brass">{category}</h3>
            <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(byBracket).map(([bracket, bracketMatches]) => {
                const byRound = groupBy(bracketMatches, (m) => m.round_name ?? '—')
                return (
                  <div key={bracket} className="plate rounded-[var(--radius-rivet)] p-4">
                    <p className="text-eyebrow text-steel">{BRACKET_LABEL[bracket] ?? bracket}</p>
                    <div className="mt-3 space-y-4">
                      {Object.entries(byRound).map(([round, roundMatches]) => (
                        <div key={round}>
                          <p className="mb-2 font-mono text-xs text-steel">{round}</p>
                          <div className="space-y-2">
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
