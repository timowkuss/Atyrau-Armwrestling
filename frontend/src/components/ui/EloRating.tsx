import { useState } from 'react'
import { Gauge } from '@/components/ui/Gauge'

interface EloRatingProps {
  eloLeft: number
  eloRight: number
  eloCombined: number
}

// Диапазон циферблата для Эло. У новых спортсменов рейтинг стартует с
// 1000 (см. backend/app/db/models/statistics.py), 700..1900 даёт запас
// с обеих сторон и не прижимает стрелку к упору на старте.
const ELO_MIN = 700
const ELO_MAX = 1900

/**
 * Карточка рейтинга Эло спортсмена. Свёрнуто показывает общий рейтинг
 * — (elo_left + elo_right) / 2 — крупной цифрой. По клику раскрывается
 * в два отдельных циферблата, левая и правая рука, как договаривались.
 */
export function EloRating({ eloLeft, eloRight, eloCombined }: EloRatingProps) {
  const [open, setOpen] = useState(false)
  const diff = eloLeft - eloRight

  return (
    <div className="plate overflow-hidden rounded-[var(--radius-rivet)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 p-4 text-left transition-colors hover:bg-bone/[0.03]"
      >
        <div>
          <div className="text-eyebrow text-brass">Общий рейтинг Эло</div>
          <div className="font-display text-3xl leading-tight text-bone">{eloCombined}</div>
        </div>
        <div className="flex flex-col items-center gap-1 text-steel-dim">
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            className="transition-transform duration-300"
            style={{ transform: open ? 'rotate(180deg)' : 'none' }}
          >
            <path d="M3 6l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="text-eyebrow">лев/прав</span>
        </div>
      </button>

      <div
        className="grid transition-[grid-template-rows] duration-300 ease-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="overflow-hidden">
          <div className="rivet-line" />
          <div className="flex flex-wrap items-center justify-around gap-4 p-4">
            <Gauge
              value={eloLeft}
              min={ELO_MIN}
              max={ELO_MAX}
              label="Левая рука"
              accent="rust"
              size={112}
              format={(v) => `${Math.round(v)}`}
            />
            <Gauge
              value={eloRight}
              min={ELO_MIN}
              max={ELO_MAX}
              label="Правая рука"
              accent="brass"
              size={112}
              format={(v) => `${Math.round(v)}`}
            />
          </div>
          <div className="rivet-line" />
          <div className="flex items-center justify-between px-4 py-2 font-mono text-xs text-steel-dim">
            <span>
              Разница Л−П: {diff > 0 ? `+${diff}` : diff}
            </span>
            <span>Общий: {eloCombined}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
