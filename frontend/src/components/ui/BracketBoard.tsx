import { useState } from 'react'
import type { BracketMatchOut } from '@/types/api'

// Порядок и подписи секций — как в десктопном окне сетки: сначала финал,
// затем нижняя сетка, затем верхняя (см. BracketWindow в
// armwrestling_tournament.py). Секция рендерится, только если для неё
// вообще есть матчи — например, при небольшом числе участников нижней
// сетки может не быть.
const BRACKET_ORDER: string[] = ['final', 'losers', 'winners']

const BRACKET_LABEL: Record<string, string> = {
  final: 'ФИНАЛ',
  losers: 'НИЖНЯЯ СЕТКА',
  winners: 'ВЕРХНЯЯ СЕТКА',
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

function RoundColumn({ roundName, matches, isLast }: {
  roundName: string
  matches: BracketMatchOut[]
  isLast?: boolean
}) {
  const sorted = [...matches].sort((a, b) => a.match_order - b.match_order)
  const gap = matches.length <= 2 ? 'gap-6' : matches.length <= 4 ? 'gap-4' : 'gap-3'

  return (
    <div className="flex items-stretch">
      <div className="flex flex-col items-center">
        <span className="mb-2 text-center font-mono text-[10px] uppercase tracking-wider text-steel-dim">
          {roundName.toUpperCase()}
        </span>
        <div className={`flex w-44 flex-1 flex-col justify-center ${gap}`}>
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

// Внутри секции (финал / нижняя / верхняя сетка) десктоп всегда рисует
// раунды от самого позднего к самому раннему (слева направо), то есть
// «Финал WB» левее «1/2 финала WB», а «Гранд-финал» левее переигровки.
// Поле stage — это сквозной порядковый номер стадии турнира, который уже
// расставляет движок генерации сетки на десктопе, поэтому сортируем по
// нему, а не пытаемся парсить текст раунда.
function BracketSection({ bracketKey, matches }: { bracketKey: string; matches: BracketMatchOut[] }) {
  const byRound = groupBy(matches, (m) => m.round_name ?? '—')
  const roundNames = Object.keys(byRound)

  const stageOf = (rn: string) => Math.max(...byRound[rn].map((m) => m.stage))
  const isFinal = bracketKey === 'final'
  roundNames.sort((a, b) => (isFinal ? stageOf(a) - stageOf(b) : stageOf(b) - stageOf(a)))

  const label = BRACKET_LABEL[bracketKey] ?? bracketKey

  return (
    <div>
      <p className="mb-4 font-mono text-xs uppercase tracking-wider text-steel">{label}</p>
      <div className="flex items-stretch gap-0 overflow-x-auto pb-3">
        {roundNames.map((rn, i) => (
          <RoundColumn
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

function HandBracket({ matches }: { matches: BracketMatchOut[] }) {
  const byBracket = groupBy(matches, (m) => m.bracket)
  const sections = BRACKET_ORDER.filter((key) => byBracket[key]?.length)

  return (
    <div className="space-y-10">
      {sections.map((key) => (
        <BracketSection key={key} bracketKey={key} matches={byBracket[key]} />
      ))}
    </div>
  )
}

const HAND_LABEL: Record<string, string> = {
  left: 'Левая',
  right: 'Правая',
  Both: 'Обе',
  Обе: 'Обе',
}

function extractWeight(name: string): number {
  const m = name.match(/(\d+)\s*kg/i)
  return m ? parseInt(m[1], 10) : 9999
}

function CategoryBracket({ matches }: { matches: BracketMatchOut[] }) {
  const byHand = groupBy(matches, (m) => m.hand)
  const hands = Object.keys(byHand)
  const [active, setActive] = useState(hands[0])
  const current = hands.includes(active) ? active : hands[0]

  if (hands.length <= 1) {
    return <HandBracket matches={matches} />
  }

  return (
    <div>
      <div className="mb-5 flex gap-2">
        {hands.map((hand) => (
          <button
            key={hand}
            onClick={() => setActive(hand)}
            className={`text-eyebrow rounded-[var(--radius-rivet)] border px-3 py-1.5 transition-colors ${
              hand === current
                ? 'border-brass bg-brass/15 text-brass'
                : 'border-steel-dim/40 text-steel hover:border-steel-dim hover:text-bone'
            }`}
          >
            {HAND_LABEL[hand] ?? hand}
          </button>
        ))}
      </div>
      <HandBracket matches={byHand[current]} />
    </div>
  )
}

export function BracketBoard({ matches }: { matches: BracketMatchOut[] }) {
  if (matches.length === 0) return null

  const byCategory = groupBy(matches, (m) => m.category_name)
  const sortedCategories = Object.entries(byCategory).sort(
    ([a], [b]) => extractWeight(a) - extractWeight(b)
  )

  return (
    <div className="space-y-12">
      {sortedCategories.map(([category, categoryMatches]) => (
        <div key={category}>
          <h3 className="font-display text-lg text-bone border-b border-steel-dim/20 pb-2">
            {category.replace(/\s*Both\s*/i, '').trim()}
          </h3>
          <div className="mt-5">
            <CategoryBracket matches={categoryMatches} />
          </div>
        </div>
      ))}
    </div>
  )
}
