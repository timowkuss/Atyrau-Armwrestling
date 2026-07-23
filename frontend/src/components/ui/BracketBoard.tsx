import { useMemo, useState } from 'react'
import type { BracketMatchOut } from '@/types/api'

// ════════════════════════════════════════════════════════════════════════
// Раскладка сетки — порт алгоритма BracketWindow._draw_bracket из
// desktop-app/armwrestling_tournament.py (строка ~2617). Та же геометрия:
// верхняя сетка слева направо с удвоением шага между раундами, финал —
// продолжение по X после последнего раунда верхней сетки, нижняя сетка
// снизу с чередованием "объединяющих" раундов (2 матча → 1) и "раундов
// приёма" (1 к 1). Линии рисуются по позиции матчей в раунде (match_order),
// как и в десктопе — а не по фактическим id следующего матча, которых
// в BracketMatchOut просто нет.
// ════════════════════════════════════════════════════════════════════════

const BOX_W = 200
const BOX_H = 52
const H_GAP = 36
const SLOT_H = BOX_H + 14
const L_SLOT_H = BOX_H + 14

const COLOR_W = '#2a4a6a'
const COLOR_L = '#7a3a1a'
const COLOR_F = '#8a6a10'

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

function extractWeight(name: string): number {
  const m = name.match(/(\d+)\s*kg/i)
  return m ? parseInt(m[1], 10) : 9999
}

const HAND_LABEL: Record<string, string> = {
  left: 'Левая',
  right: 'Правая',
  Both: 'Обе',
  Обе: 'Обе',
}

interface Line {
  x1: number
  y1: number
  x2: number
  y2: number
  color: string
}

interface Positioned {
  match: BracketMatchOut
  x: number
  y: number
}

interface Layout {
  positioned: Positioned[]
  lines: Line[]
  width: number
  height: number
  lowerLabel: { x: number; y: number } | null
}

// Раунды одной секции (winners / losers / final) в хронологическом порядке
// (ранний раунд первым), матчи внутри раунда — по match_order, как в
// десктопной отрисовке.
function roundsInOrder(matches: BracketMatchOut[] | undefined): BracketMatchOut[][] {
  if (!matches || matches.length === 0) return []
  const byRound = groupBy(matches, (m) => m.round_name ?? '—')
  const names = Object.keys(byRound)
  const stageOf = (rn: string) => Math.min(...byRound[rn].map((m) => m.stage))
  names.sort((a, b) => stageOf(a) - stageOf(b))
  return names.map((rn) => [...byRound[rn]].sort((a, b) => a.match_order - b.match_order))
}

function layoutBracket(matches: BracketMatchOut[]): Layout {
  const positioned: Positioned[] = []
  const lines: Line[] = []
  const byBracket = groupBy(matches, (m) => m.bracket)

  const wRounds = roundsInOrder(byBracket.winners)
  const lRounds = roundsInOrder(byBracket.losers)
  const fRounds = roundsInOrder(byBracket.final)

  const X_START = 0
  const Y_W_START = 0

  const yPos = (matchIdx: number, roundIdx: number) => {
    const step = SLOT_H * 2 ** roundIdx
    const firstCenter = Y_W_START + (step - BOX_H) / 2
    return firstCenter + matchIdx * step
  }

  // ── Верхняя сетка ──
  const wColX: number[] = []
  const wYPositions: number[][] = []

  wRounds.forEach((roundMatches, ri) => {
    const x = X_START + ri * (BOX_W + H_GAP)
    const colYs: number[] = []
    roundMatches.forEach((m, mi) => {
      const y = yPos(mi, ri)
      positioned.push({ match: m, x, y })
      colYs.push(y)
    })
    wColX.push(x)
    wYPositions.push(colYs)
  })

  wRounds.forEach((_roundMatches, ri) => {
    if (ri + 1 >= wRounds.length) return
    const colYs = wYPositions[ri]
    if (colYs.length < 2) return
    const x = wColX[ri]
    const xMid = x + BOX_W + H_GAP / 2
    const xNext = x + BOX_W + H_GAP
    for (let p = 0; p < colYs.length; p += 2) {
      if (p + 1 >= colYs.length) continue
      const y1 = colYs[p] + BOX_H / 2
      const y2 = colYs[p + 1] + BOX_H / 2
      const yMid = (y1 + y2) / 2
      lines.push({ x1: x + BOX_W, y1, x2: xMid, y2: y1, color: COLOR_W })
      lines.push({ x1: x + BOX_W, y1: y2, x2: xMid, y2, color: COLOR_W })
      lines.push({ x1: xMid, y1, x2: xMid, y2, color: COLOR_W })
      lines.push({ x1: xMid, y1: yMid, x2: xNext, y2: yMid, color: COLOR_W })
    }
  })

  let maxYW = Y_W_START
  wYPositions.forEach((colYs) => colYs.forEach((y) => { maxYW = Math.max(maxYW, y + BOX_H) }))

  // ── Финал — продолжение по X после последней колонки верхней сетки ──
  const xFinal = X_START + wRounds.length * (BOX_W + H_GAP)
  const yFinal = Y_W_START

  fRounds.forEach((roundMatches, fi) => {
    const xThis = xFinal + fi * (BOX_W + H_GAP)
    roundMatches.forEach((m) => {
      const isReset = (m.round_name ?? '').toLowerCase().includes('переигровка')
      if (isReset && !(m.p1_name && m.p2_name) && m.status !== 'done') return
      positioned.push({ match: m, x: xThis, y: yFinal })
    })
  })

  if (fRounds.length > 0 && wColX.length > 0) {
    const xPrev = wColX[wColX.length - 1] + BOX_W
    const xMid = xPrev + H_GAP / 2
    const lastCol = wYPositions[wYPositions.length - 1]
    const yWf = lastCol && lastCol.length > 0 ? lastCol[0] + BOX_H / 2 : yFinal + BOX_H / 2
    const yF = yFinal + BOX_H / 2
    lines.push({ x1: xPrev, y1: yWf, x2: xMid, y2: yWf, color: COLOR_F })
    lines.push({ x1: xMid, y1: yWf, x2: xMid, y2: yF, color: COLOR_F })
    lines.push({ x1: xMid, y1: yF, x2: xFinal, y2: yF, color: COLOR_F })
  }

  // ── Нижняя сетка ──
  const Y_L_START = maxYW + 50
  const lColPositions: { x: number; ys: number[] }[] = []

  lRounds.forEach((roundMatches, ri) => {
    const x = X_START + (ri + 1) * (BOX_W + H_GAP)
    const stepMult = 2 ** Math.floor(ri / 2)
    const step = L_SLOT_H * stepMult
    const firstOffset = (step - L_SLOT_H) / 2
    const colYs: number[] = []
    roundMatches.forEach((m, mi) => {
      const y = Y_L_START + firstOffset + mi * step
      positioned.push({ match: m, x, y })
      colYs.push(y)
    })
    lColPositions.push({ x, ys: colYs })
  })

  for (let ri = 0; ri < lColPositions.length - 1; ri++) {
    const { x: xCur, ys: ysCur } = lColPositions[ri]
    const { x: xNxt, ys: ysNxt } = lColPositions[ri + 1]
    const xOut = xCur + BOX_W
    const xMid = xOut + H_GAP / 2
    const xIn = xNxt
    const isMerging = ysNxt.length < ysCur.length

    if (isMerging) {
      for (let p = 0; p < ysCur.length; p += 2) {
        if (p + 1 < ysCur.length) {
          const y1 = ysCur[p] + BOX_H / 2
          const y2 = ysCur[p + 1] + BOX_H / 2
          const targetIdx = Math.floor(p / 2)
          if (targetIdx < ysNxt.length) {
            const yTarget = ysNxt[targetIdx] + BOX_H / 2
            lines.push({ x1: xOut, y1, x2: xMid, y2: y1, color: COLOR_L })
            lines.push({ x1: xOut, y1: y2, x2: xMid, y2, color: COLOR_L })
            lines.push({ x1: xMid, y1, x2: xMid, y2, color: COLOR_L })
            lines.push({ x1: xMid, y1: yTarget, x2: xIn, y2: yTarget, color: COLOR_L })
          }
        } else {
          const y1 = ysCur[p] + BOX_H / 2
          const targetIdx = Math.floor(p / 2)
          if (targetIdx < ysNxt.length) {
            const yTarget = ysNxt[targetIdx] + BOX_H / 2
            lines.push({ x1: xOut, y1, x2: xMid, y2: y1, color: COLOR_L })
            lines.push({ x1: xMid, y1, x2: xMid, y2: yTarget, color: COLOR_L })
            lines.push({ x1: xMid, y1: yTarget, x2: xIn, y2: yTarget, color: COLOR_L })
          }
        }
      }
    } else {
      ysCur.forEach((yCur, mi) => {
        if (mi < ysNxt.length) {
          const yFrom = yCur + BOX_H / 2
          const yTo = ysNxt[mi] + BOX_H / 2
          lines.push({ x1: xOut, y1: yFrom, x2: xMid, y2: yFrom, color: COLOR_L })
          lines.push({ x1: xMid, y1: yFrom, x2: xMid, y2: yTo, color: COLOR_L })
          lines.push({ x1: xMid, y1: yTo, x2: xIn, y2: yTo, color: COLOR_L })
        }
      })
    }
  }

  let width = xFinal + fRounds.length * (BOX_W + H_GAP) + 40
  let height = maxYW + 40
  let lowerLabel: Layout['lowerLabel'] = null

  if (lColPositions.length > 0) {
    lowerLabel = { x: X_START, y: Y_L_START - 22 }
    const xLEnd = X_START + (lColPositions.length + 1) * (BOX_W + H_GAP) + 40
    width = Math.max(width, xLEnd)
    let maxLY = Y_L_START
    lRounds.forEach((roundMatches, ri) => {
      const stepMult = 2 ** Math.floor(ri / 2)
      const step = L_SLOT_H * stepMult
      const firstOffset = (step - L_SLOT_H) / 2
      const bottom = Y_L_START + firstOffset + (roundMatches.length - 1) * step + BOX_H
      maxLY = Math.max(maxLY, bottom)
    })
    height = maxLY + 40
  }

  return { positioned, lines, width, height, lowerLabel }
}

// ════════════════════════════════════════════════════════════════════════
//  Рендер
// ════════════════════════════════════════════════════════════════════════

function MatchBox({ match, x, y }: { match: BracketMatchOut; x: number; y: number }) {
  const isDone = match.status === 'done' || match.status === 'bye'
  const isBye = match.status === 'bye'
  const p1Won = isDone && match.winner_name != null && match.winner_name === match.p1_name
  const p2Won = isDone && match.winner_name != null && match.winner_name === match.p2_name

  return (
    <div
      className={`absolute flex flex-col justify-center rounded-[var(--radius-rivet)] border px-3 py-1.5 ${
        isDone ? 'border-brass/30 bg-brass/5' : 'border-steel-dim/25 bg-black/20'
      }`}
      style={{ left: x, top: y, width: BOX_W, height: BOX_H }}
    >
      <div className="flex items-center gap-2">
        <div className={`h-1.5 w-1.5 shrink-0 rounded-full ${isDone ? 'bg-brass' : 'bg-steel-dim/40'}`} />
        <p
          className={`truncate text-xs leading-tight ${
            p1Won ? 'font-medium text-brass' : isBye ? 'italic text-steel-dim' : 'text-bone'
          }`}
        >
          {match.p1_name ?? 'TBD'}
        </p>
        {p1Won && <span className="ml-auto shrink-0 text-[9px] text-brass/70">★</span>}
      </div>
      <div className="my-0.5 h-px bg-steel-dim/15" />
      <div className="flex items-center gap-2">
        <div className={`h-1.5 w-1.5 shrink-0 rounded-full ${isDone && !isBye ? 'bg-brass' : 'bg-steel-dim/40'}`} />
        <p
          className={`truncate text-xs leading-tight ${
            p2Won ? 'font-medium text-brass' : isBye ? 'italic text-steel-dim' : 'text-bone'
          }`}
        >
          {match.p2_name ?? 'TBD'}
        </p>
        {p2Won && <span className="ml-auto shrink-0 text-[9px] text-brass/70">★</span>}
      </div>
    </div>
  )
}

function BracketTree({ matches }: { matches: BracketMatchOut[] }) {
  const layout = useMemo(() => layoutBracket(matches), [matches])
  if (layout.positioned.length === 0) return null

  return (
    <div className="overflow-x-auto pb-3">
      <div className="relative" style={{ width: layout.width, height: layout.height, minWidth: layout.width }}>
        <svg className="absolute inset-0" width={layout.width} height={layout.height}>
          {layout.lines.map((l, i) => (
            <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke={l.color} strokeWidth={1} />
          ))}
        </svg>
        {layout.lowerLabel && (
          <p
            className="absolute font-mono text-[11px] font-bold uppercase tracking-wider text-rust"
            style={{ left: layout.lowerLabel.x, top: layout.lowerLabel.y }}
          >
            ⬇ Нижняя сетка (Losers Bracket)
          </p>
        )}
        {layout.positioned.map(({ match, x, y }) => (
          <MatchBox key={match.id} match={match} x={x} y={y} />
        ))}
      </div>
    </div>
  )
}

function CategoryBracket({ matches }: { matches: BracketMatchOut[] }) {
  const byHand = groupBy(matches, (m) => m.hand)
  const hands = Object.keys(byHand)
  const [active, setActive] = useState(hands[0])
  const current = hands.includes(active) ? active : hands[0]

  if (hands.length <= 1) {
    return <BracketTree matches={matches} />
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
      <BracketTree matches={byHand[current]} />
    </div>
  )
}

export function BracketBoard({ matches }: { matches: BracketMatchOut[] }) {
  if (matches.length === 0) return null

  const byCategory = groupBy(matches, (m) => m.category_name)
  const sortedCategories = Object.entries(byCategory).sort(
    ([a], [b]) => extractWeight(a) - extractWeight(b),
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
