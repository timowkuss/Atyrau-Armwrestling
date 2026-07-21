import type { BracketMatchOut } from '@/types/api'

const BRACKET_LABEL: Record<string, string> = {
  winners: 'Верхняя сетка',
  losers: 'Нижняя сетка',
  final: 'Финал',
}

const ROUND_LABEL: Record<string, string> = {
  '1/2 финала': '1/2',
  '1/4 финала': '1/4',
  'Финал': 'Финал',
  'Утешительный финал': 'Утешит.',
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

function MatchCard({ match, compact }: { match: BracketMatchOut; compact?: boolean }) {
  const isDone = match.status === 'done' || match.status === 'bye'
  const p1Won = isDone && match.winner_name != null && match.winner_name === match.p1_name
  const p2Won = isDone && match.winner_name != null && match.winner_name === match.p2_name
  const isBye = match.status === 'bye'

  return (
    <div className={`relative rounded border ${
      isDone
        ? 'border-brass/30 bg-brass/5'
        : 'border-steel-dim/25 bg-black/20'
    } ${compact ? 'px-3 py-2' : 'px-4 py-3'}`}>
      <div className="flex items-center gap-2">
        <div className={`h-1.5 w-1.5 rounded-full shrink-0 ${
          isDone ? 'bg-brass' : 'bg-steel-dim/40'
        }`} />
        <p className={`truncate text-sm ${
          p1Won ? 'font-medium text-brass' : isBye ? 'text-steel-dim italic' : 'text-bone'
        }`}>
          {match.p1_name ?? 'TBD'}
        </p>
        {p1Won && <span className="ml-auto shrink-0 text-[10px] text-brass/70">★</span>}
      </div>
      <div className="my-1 h-px bg-steel-dim/15" />
      <div className="flex items-center gap-2">
        <div className={`h-1.5 w-1.5 rounded-full shrink-0 ${
          isDone && !isBye ? 'bg-brass' : 'bg-steel-dim/40'
        }`} />
        <p className={`truncate text-sm ${
          p2Won ? 'font-medium text-brass' : isBye ? 'text-steel-dim italic' : 'text-bone'
        }`}>
          {match.p2_name ?? 'TBD'}
        </p>
        {p2Won && <span className="ml-auto shrink-0 text-[10px] text-brass/70">★</span>}
      </div>
    </div>
  )
}

function BracketColumn({ roundName, matches, isLast }: {
  roundName: string
  matches: BracketMatchOut[]
  isLast?: boolean
}) {
  const label = ROUND_LABEL[roundName] ?? roundName
  const sorted = [...matches].sort((a, b) => a.match_order - b.match_order)
  const gap = matches.length <= 2 ? 'gap-6' : matches.length <= 4 ? 'gap-4' : 'gap-3'

  return (
    <div className="flex items-stretch">
      <div className="flex flex-col items-center">
        <span className="mb-2 text-center font-mono text-[10px] uppercase tracking-wider text-steel-dim">
          {label}
        </span>
        <div className={`flex flex-1 flex-col justify-center ${gap}`}>
          {sorted.map((m) => (
            <MatchCard key={m.id} match={m} compact={matches.length > 3} />
          ))}
        </div>
      </div>
      {!isLast && (
        <div className="flex w-6 items-center justify-center self-stretch">
          <div className="h-full w-px bg-gradient-to-b from-transparent via-steel-dim/30 to-transparent" />
        </div>
      )}
    </div>
  )
}

function BracketGrid({ matches, label }: { matches: BracketMatchOut[]; label?: string }) {
  const byRound = groupBy(matches, (m) => m.round_name ?? '—')
  const roundNames = Object.keys(byRound).sort((a, b) => {
    const order = ['Финал', 'Утешительный финал', '1/2 финала', '1/4 финала', '1/8 финала', '1/16 финала']
    const ia = order.indexOf(a)
    const ib = order.indexOf(b)
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
  })

  if (roundNames.length === 1) {
    return (
      <div>
        {label && <p className="mb-3 text-eyebrow text-steel">{label}</p>}
        <div className="space-y-3">
          {[...matches].sort((a, b) => a.match_order - b.match_order).map((m) => (
            <MatchCard key={m.id} match={m} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div>
      {label && <p className="mb-4 text-eyebrow text-steel">{label}</p>}
      <div className="flex items-stretch overflow-x-auto pb-2">
        {roundNames.map((rn, i) => (
          <BracketColumn
            key={rn}
            roundName={rn}
            matches={byRound[rn]}
            isLast={i === roundNames.length - 1}
          />
        ))}
      </div>
    </div>
  )
}

export function BracketBoard({ matches }: { matches: BracketMatchOut[] }) {
  if (matches.length === 0) return null

  const byCategory = groupBy(matches, (m) => m.category_name)

  return (
    <div className="space-y-12">
      {Object.entries(byCategory).map(([category, categoryMatches]) => {
        const byHand = groupBy(categoryMatches, (m) => m.hand)
        const hands = Object.keys(byHand)
        const showHandLabel = hands.length > 1

        return (
          <div key={category}>
            <h3 className="font-display text-lg text-bone border-b border-steel-dim/20 pb-2">
              {category}
            </h3>
            <div className={showHandLabel ? 'mt-5 space-y-10' : 'mt-5'}>
              {hands.map((hand) => {
                const handMatches = byHand[hand]
                const byBracket = groupBy(handMatches, (m) => m.bracket)
                return (
                  <div key={hand}>
                    {showHandLabel && (
                      <p className="mb-3 font-mono text-xs uppercase tracking-wider text-emerald-400">
                        {hand} рука
                      </p>
                    )}
                    <div className="grid gap-8 sm:grid-cols-2 xl:grid-cols-3">
                      {Object.entries(byBracket).map(([bracket, bracketMatches]) => (
                        <BracketGrid
                          key={bracket}
                          matches={bracketMatches}
                          label={BRACKET_LABEL[bracket] ?? bracket}
                        />
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
