import { useEffect, useMemo, useState } from 'react'
import type { BracketMatchOut } from '@/types/api'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'

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

// На мобильных — компактная геометрия: у́же боксы, меньший шаг, чтобы
// вся сетка читалась при горизонтальной прокрутке.
const COMPACT = { boxW: 150, hGap: 20, boxH: 52 }
const FULL = { boxW: 220, hGap: 36, boxH: 64 }

const COLOR_W = '#2a4a6a'
const COLOR_L = '#7a3a1a'
const COLOR_F = '#8a6a10'

function useCompact(): boolean {
  const [compact, setCompact] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)')
    const onChange = () => setCompact(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return compact
}

type Geometry = { boxW: number; hGap: number; boxH: number }

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
// десктопной отрисовке. Группируем по round_name, но если он пустой
// (например, на проде у single-elimination 1/4 и 1/2 остались без имени) —
// фолбэк на stage, иначе разные раунды слипаются в одну колонку.
function roundsInOrder(matches: BracketMatchOut[] | undefined): BracketMatchOut[][] {
  if (!matches || matches.length === 0) return []
  const keyOf = (m: BracketMatchOut) => (m.round_name?.trim() ? m.round_name : `stage:${m.stage}`)
  const byRound = groupBy(matches, keyOf)
  const names = Object.keys(byRound)
  const stageOf = (rn: string) => Math.min(...byRound[rn].map((m) => m.stage))
  names.sort((a, b) => stageOf(a) - stageOf(b))
  return names.map((rn) => [...byRound[rn]].sort((a, b) => a.match_order - b.match_order))
}

function layoutBracket(matches: BracketMatchOut[], g: Geometry): Layout {
  const { boxW, hGap, boxH } = g
  const slotH = boxH + 14
  const lSlotH = boxH + 14
  const positioned: Positioned[] = []
  const lines: Line[] = []
  const byBracket = groupBy(matches, (m) => m.bracket)

  const wRounds = roundsInOrder(byBracket.winners)
  const lRounds = roundsInOrder(byBracket.losers)
  const fRounds = roundsInOrder(byBracket.final)

  const X_START = 0
  const Y_W_START = 0

  const yPos = (matchIdx: number, roundIdx: number) => {
    const step = slotH * 2 ** roundIdx
    const firstCenter = Y_W_START + (step - boxH) / 2
    return firstCenter + matchIdx * step
  }

  // ── Верхняя сетка ──
  const wColX: number[] = []
  const wYPositions: number[][] = []

  wRounds.forEach((roundMatches, ri) => {
    const x = X_START + ri * (boxW + hGap)
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
    const xMid = x + boxW + hGap / 2
    const xNext = x + boxW + hGap
    for (let p = 0; p < colYs.length; p += 2) {
      if (p + 1 >= colYs.length) continue
      const y1 = colYs[p] + boxH / 2
      const y2 = colYs[p + 1] + boxH / 2
      const yMid = (y1 + y2) / 2
      lines.push({ x1: x + boxW, y1, x2: xMid, y2: y1, color: COLOR_W })
      lines.push({ x1: x + boxW, y1: y2, x2: xMid, y2, color: COLOR_W })
      lines.push({ x1: xMid, y1, x2: xMid, y2, color: COLOR_W })
      lines.push({ x1: xMid, y1: yMid, x2: xNext, y2: yMid, color: COLOR_W })
    }
  })

  let maxYW = Y_W_START
  wYPositions.forEach((colYs) => colYs.forEach((y) => { maxYW = Math.max(maxYW, y + boxH) }))

  // ── Финал — продолжение по X после последней колонки верхней сетки ──
  const xFinal = X_START + wRounds.length * (boxW + hGap)
  const yFinal = Y_W_START

  fRounds.forEach((roundMatches, fi) => {
    const xThis = xFinal + fi * (boxW + hGap)
    roundMatches.forEach((m) => {
      const isReset = (m.round_name ?? '').toLowerCase().includes('переигровка')
      if (isReset && !(m.p1_name && m.p2_name) && m.status !== 'done') return
      positioned.push({ match: m, x: xThis, y: yFinal })
    })
  })

  if (fRounds.length > 0 && wColX.length > 0) {
    const xPrev = wColX[wColX.length - 1] + boxW
    const xMid = xPrev + hGap / 2
    const lastCol = wYPositions[wYPositions.length - 1]
    const yWf = lastCol && lastCol.length > 0 ? lastCol[0] + boxH / 2 : yFinal + boxH / 2
    const yF = yFinal + boxH / 2
    lines.push({ x1: xPrev, y1: yWf, x2: xMid, y2: yWf, color: COLOR_F })
    lines.push({ x1: xMid, y1: yWf, x2: xMid, y2: yF, color: COLOR_F })
    lines.push({ x1: xMid, y1: yF, x2: xFinal, y2: yF, color: COLOR_F })
  }

  // ── Нижняя сетка ──
  const Y_L_START = maxYW + 50
  const lColPositions: { x: number; ys: number[] }[] = []

  lRounds.forEach((roundMatches, ri) => {
    const x = X_START + (ri + 1) * (boxW + hGap)
    const stepMult = 2 ** Math.floor(ri / 2)
    const step = lSlotH * stepMult
    const firstOffset = (step - lSlotH) / 2
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
    const xOut = xCur + boxW
    const xMid = xOut + hGap / 2
    const xIn = xNxt
    const isMerging = ysNxt.length < ysCur.length

    if (isMerging) {
      for (let p = 0; p < ysCur.length; p += 2) {
        if (p + 1 < ysCur.length) {
          const y1 = ysCur[p] + boxH / 2
          const y2 = ysCur[p + 1] + boxH / 2
          const targetIdx = Math.floor(p / 2)
          if (targetIdx < ysNxt.length) {
            const yTarget = ysNxt[targetIdx] + boxH / 2
            lines.push({ x1: xOut, y1, x2: xMid, y2: y1, color: COLOR_L })
            lines.push({ x1: xOut, y1: y2, x2: xMid, y2, color: COLOR_L })
            lines.push({ x1: xMid, y1, x2: xMid, y2, color: COLOR_L })
            lines.push({ x1: xMid, y1: yTarget, x2: xIn, y2: yTarget, color: COLOR_L })
          }
        } else {
          const y1 = ysCur[p] + boxH / 2
          const targetIdx = Math.floor(p / 2)
          if (targetIdx < ysNxt.length) {
            const yTarget = ysNxt[targetIdx] + boxH / 2
            lines.push({ x1: xOut, y1, x2: xMid, y2: y1, color: COLOR_L })
            lines.push({ x1: xMid, y1, x2: xMid, y2: yTarget, color: COLOR_L })
            lines.push({ x1: xMid, y1: yTarget, x2: xIn, y2: yTarget, color: COLOR_L })
          }
        }
      }
    } else {
      ysCur.forEach((yCur, mi) => {
        if (mi < ysNxt.length) {
          const yFrom = yCur + boxH / 2
          const yTo = ysNxt[mi] + boxH / 2
          lines.push({ x1: xOut, y1: yFrom, x2: xMid, y2: yFrom, color: COLOR_L })
          lines.push({ x1: xMid, y1: yFrom, x2: xMid, y2: yTo, color: COLOR_L })
          lines.push({ x1: xMid, y1: yTo, x2: xIn, y2: yTo, color: COLOR_L })
        }
      })
    }
  }

  let width = xFinal + fRounds.length * (boxW + hGap) + 40
  let height = maxYW + 40
  let lowerLabel: Layout['lowerLabel'] = null

  if (lColPositions.length > 0) {
    lowerLabel = { x: X_START, y: Y_L_START - 22 }
    const xLEnd = X_START + (lColPositions.length + 1) * (boxW + hGap) + 40
    width = Math.max(width, xLEnd)
    let maxLY = Y_L_START
    lRounds.forEach((roundMatches, ri) => {
      const stepMult = 2 ** Math.floor(ri / 2)
      const step = lSlotH * stepMult
      const firstOffset = (step - lSlotH) / 2
      const bottom = Y_L_START + firstOffset + (roundMatches.length - 1) * step + boxH
      maxLY = Math.max(maxLY, bottom)
    })
    height = maxLY + 40
  }

  return { positioned, lines, width, height, lowerLabel }
}

// ════════════════════════════════════════════════════════════════════════
//  Рендер
// ════════════════════════════════════════════════════════════════════════

// Пустой слот: "BYE" только если матч структурно является BYE (см.
// _draw_match_box в десктопе — pname()), иначе слот просто ждёт
// победителя предыдущего матча — пишем "— ожидание —", а не "TBD".
function slotLabel(name: string | null, isByeMatch: boolean): string {
  if (name) return name
  return isByeMatch ? 'BYE' : '— ожидание —'
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
}

function RowLabel({ name, photo, isBye }: { name: string | null; photo: string | null; isBye: boolean }) {
  const src = cloudinaryThumb(photo, 48)
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className="h-6 w-6 shrink-0 overflow-hidden rounded-md bg-steel-dim/20 ring-1 ring-steel-dim/30">
        {src && name ? (
          <img src={src} alt={name} className="h-full w-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-[10px] font-mono text-bone/70">
            {name ? initials(name) : '—'}
          </span>
        )}
      </span>
      <span className="min-w-0 flex-1 truncate">{slotLabel(name, isBye)}</span>
    </span>
  )
}

function MatchBox({ match, x, y, g }: { match: BracketMatchOut; x: number; y: number; g: Geometry }) {
  const { boxW, boxH } = g
  const isByeMatch = match.status === 'bye'
  const hasWinner = match.winner_name != null
  const p1Won = hasWinner && match.winner_name === match.p1_name
  const p2Won = hasWinner && match.winner_name === match.p2_name

  const boxClass = hasWinner
    ? 'border border-brass/30 bg-brass/5'
    : 'border border-steel-dim/25 bg-black/20'

  const rowClass = (won: boolean, lost: boolean, name: string | null) => {
    if (won) return 'font-medium text-emerald-400'
    if (lost) return 'text-red-400'
    if (!name) return 'italic text-steel-dim'
    return 'text-bone'
  }

  return (
    <div
      className={`absolute flex flex-col justify-center rounded-[var(--radius-rivet)] px-2 py-1 ${boxClass}`}
      style={{
        left: x,
        top: y,
        width: boxW,
        height: boxH,
      }}
    >
      <div className="flex items-center justify-between gap-1.5">
        <div className={`min-w-0 truncate text-[11px] leading-tight sm:text-xs ${rowClass(p1Won, hasWinner && p2Won, match.p1_name)}`}>
          <RowLabel name={match.p1_name} photo={match.p1_photo} isBye={isByeMatch} />
        </div>
      </div>
      <div className="my-0.5 h-px bg-steel-dim/15" />
      <div className={`min-w-0 truncate text-[11px] leading-tight sm:text-xs ${rowClass(p2Won, hasWinner && p1Won, match.p2_name)}`}>
        <RowLabel name={match.p2_name} photo={match.p2_photo} isBye={isByeMatch} />
      </div>
    </div>
  )
}

export function BracketTree({ matches }: { matches: BracketMatchOut[] }) {
  const compact = useCompact()
  const g = compact ? COMPACT : FULL
  const layout = useMemo(() => layoutBracket(matches, g), [matches, g])
  if (layout.positioned.length === 0) return null

  return (
    <div className="overflow-x-auto overscroll-x-contain pb-3">
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
          <MatchBox key={match.id} match={match} x={x} y={y} g={g} />
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
      <div className="mb-5 flex flex-wrap gap-2">
        {hands.map((hand) => (
          <button
            key={hand}
            onClick={() => setActive(hand)}
            className={`text-eyebrow whitespace-nowrap rounded-[var(--radius-rivet)] border px-3 py-1.5 transition-colors ${
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
