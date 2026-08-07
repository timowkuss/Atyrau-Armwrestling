import { useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useCompetition, useCompetitionQueue } from '@/features/competitions/useCompetitions'
import type { TableQueueOut, QueuePairOut } from '@/types/api'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'

function tabloRoundName(roundName: string | null): string | null {
  if (!roundName) return null
  if (roundName === 'Суперфинал (переигровка)' || roundName === 'Финал' || roundName === 'Полуфинал') return roundName
  if (roundName.includes('переигровка')) return 'Суперфинал (переигровка)'
  if (roundName.includes('Гранд-финал') || roundName.includes('Финал')) return 'Финал'
  if (roundName.includes('1/2') || roundName.includes('Раунд')) return 'Полуфинал'
  return null
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

function FighterChip({ name, photo, compact }: { name: string; photo: string | null; compact?: boolean }) {
  const src = cloudinaryThumb(photo, compact ? 96 : 192)
  return (
    <div className={`flex items-center gap-2.5 ${compact ? 'flex-row' : 'flex-col sm:flex-row'}`}>
      <div
        className={`shrink-0 overflow-hidden bg-steel-dim/20 ring-1 ring-steel-dim/30 ${
          compact ? 'h-12 w-12 rounded-lg' : 'h-20 w-20 rounded-xl sm:h-28 sm:w-28'
        }`}
      >
        {src ? (
          <img src={src} alt={name} className="h-full w-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <span className={`flex h-full w-full items-center justify-center font-mono text-bone ${compact ? 'text-base' : 'text-2xl sm:text-4xl'}`}>
            {initials(name)}
          </span>
        )}
      </div>
      <span className={`text-bone ${compact ? 'text-sm' : 'text-base sm:text-xl'}`}>{name}</span>
    </div>
  )
}

function PairBlock({ pair, label, compact }: { pair: QueuePairOut; label?: string; compact?: boolean }) {
  const displayRound = tabloRoundName(pair.round_name)
  return (
    <div className="flex flex-col items-center gap-0.5">
      {label && <p className="text-[10px] uppercase tracking-widest text-emerald-400">{label}</p>}
      {displayRound && (
        <p className="font-mono text-[9px] uppercase tracking-wider text-brass">{displayRound}</p>
      )}
      <div className="flex items-center justify-center gap-4 sm:gap-6">
        <div className={`flex flex-col items-center ${compact ? 'max-w-[42%]' : 'max-w-[44%]'} text-center`}>
          <FighterChip name={pair.p1_name} photo={pair.p1_photo} compact={compact} />
        </div>
        <span className={`font-mono text-steel font-normal shrink-0 ${compact ? 'text-sm' : 'text-2xl sm:text-3xl'}`}>vs</span>
        <div className={`flex flex-col items-center ${compact ? 'max-w-[42%]' : 'max-w-[44%]'} text-center`}>
          <FighterChip name={pair.p2_name} photo={pair.p2_photo} compact={compact} />
        </div>
      </div>
    </div>
  )
}

function QueueBlock({ table, tableCount }: { table: TableQueueOut; tableCount: number }) {
  const hasMatch = !!table.current
  const hasStandings = table.eliminated.length > 0
  const isComplete = !hasMatch && hasStandings
  const categoryLabel = table.category_name.replace(/\s*Both\s*/i, '').trim()
  const handLabel = table.hand
  const isSingle = tableCount === 1

  return (
    <div className={`flex flex-col border border-steel-dim/20 bg-black/20 ${isSingle ? 'p-6 sm:p-10' : 'p-3 sm:p-4'}`}>
      <div className="text-center mb-2">
        {isComplete ? (
          <p className={`font-display font-bold uppercase tracking-[0.25em] text-emerald-400 ${isSingle ? 'text-2xl sm:text-3xl' : 'text-lg sm:text-xl'}`}>
            {categoryLabel} <span className="text-steel-dim">|</span> {handLabel}
          </p>
        ) : (
          <>
            <p className={`font-display font-bold uppercase tracking-[0.25em] text-emerald-400 ${isSingle ? 'text-2xl sm:text-3xl' : 'text-lg sm:text-xl'}`}>
              Стол {table.table_number}
            </p>
            <p className="font-mono text-[10px] text-steel-dim mt-0.5">
              {categoryLabel} | {handLabel} рука
            </p>
          </>
        )}
      </div>

      {hasMatch ? (
        <div className={`border-b border-steel-dim/10 ${isSingle ? 'py-6' : 'py-2'}`}>
          <PairBlock pair={table.current!} label="сейчас" />
        </div>
      ) : isComplete ? (
        <div className={`border-b border-steel-dim/10 ${isSingle ? 'py-6' : 'py-2'}`}>
          <p className="text-center font-mono text-[10px] uppercase tracking-wider text-steel-dim">Турнир завершён</p>
        </div>
      ) : (
        <div className={`border-b border-steel-dim/10 ${isSingle ? 'py-6' : 'py-2'}`}>
          <p className="text-center text-sm text-steel-dim">Ожидание</p>
        </div>
      )}

      {table.next.length > 0 ? (
        <div className={`border-b border-steel-dim/10 ${isSingle ? 'py-4 space-y-3' : 'py-2 space-y-2'}`}>
          {table.next.map((pair, i) => (
            <PairBlock key={pair.match_id} pair={pair} label={i === 0 ? 'далее' : undefined} compact />
          ))}
        </div>
      ) : hasMatch ? (
        <div className={`border-b border-steel-dim/10 ${isSingle ? 'py-4' : 'py-2'}`}>
          <p className="text-center text-sm text-steel-dim">Следующая пара не готова</p>
        </div>
      ) : null}

      {hasStandings && (
        <div className={`${isSingle ? 'pt-3 space-y-1' : 'pt-1.5 space-y-0.5'}`}>
          {table.eliminated.map((e) => {
            const elimSize = isSingle
              ? table.eliminated.length >= 12 ? 'text-[11px]'
                : table.eliminated.length >= 8 ? 'text-xs'
                : 'text-sm'
              : table.eliminated.length >= 16 ? 'text-[9px]'
                : 'text-[11px]'
            return (
              <p key={e.athlete_name} className={`flex items-center gap-1.5 text-left font-mono text-steel-dim ${elimSize}`}>
                <span className="inline-block w-5 shrink-0 text-right">{e.place}.</span>
                <span className="h-5 w-5 shrink-0 overflow-hidden rounded-md bg-steel-dim/20 ring-1 ring-steel-dim/30">
                  {cloudinaryThumb(e.photo_path, 40) ? (
                    <img src={cloudinaryThumb(e.photo_path, 40)!} alt="" className="h-full w-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
                  ) : null}
                </span>
                <span className="truncate text-bone">{e.athlete_name}</span>
                {e.wins > 0 || e.losses > 0 ? (
                  <span className="ml-1 shrink-0 text-steel-dim/50">{e.wins}-{e.losses}</span>
                ) : null}
              </p>
            )
          })}
        </div>
      )}
    </div>
  )
}

function CategoryFilter({
  categories,
  value,
  onSelect,
}: {
  categories: { id: number; name: string }[]
  value: string | null
  onSelect: (name: string | null) => void
}) {
  if (categories.length === 0) return null

  return (
    <div className="mt-4 flex items-center justify-center gap-2">
      <label className="font-mono text-[10px] uppercase tracking-wider text-steel-dim">Категория</label>
      <select
        value={value ?? ''}
        onChange={(e) => onSelect(e.target.value === '' ? null : e.target.value)}
        className="rounded-md border border-steel-dim/30 bg-ink px-3 py-1.5 font-mono text-sm text-bone outline-none transition-colors hover:border-steel-dim focus:border-emerald-400"
      >
        <option value="">Все категории</option>
        {categories.map((c) => (
          <option key={c.id} value={c.name}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  )
}

export function CompetitionBoard() {
  const { id } = useParams<{ id: string }>()
  const competitionId = Number(id)

  const competition = useCompetition(competitionId)
  const queue = useCompetitionQueue(competitionId)
  const [searchParams, setSearchParams] = useSearchParams()

  const selectedNames = useMemo(() => {
    const raw = searchParams.get('categories')
    if (!raw) return new Set<string>()
    return new Set(raw.split(',').map((s) => decodeURIComponent(s)).filter(Boolean))
  }, [searchParams])

  const selectCategory = (name: string | null) => {
    const params = new URLSearchParams(searchParams)
    if (!name) params.delete('categories')
    else params.set('categories', encodeURIComponent(name))
    setSearchParams(params, { replace: true })
  }

  const allTables = queue.data ?? []

  const tables = useMemo(() => {
    if (selectedNames.size === 0) return allTables
    return allTables.filter((table) => selectedNames.has(table.category_name))
  }, [allTables, selectedNames])

  const gridClass = tables.length <= 1
    ? 'grid-cols-1'
    : tables.length === 2
      ? 'grid-cols-1 sm:grid-cols-2'
      : tables.length <= 4
        ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-2'
        : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'

  return (
    <div className="min-h-screen bg-ink px-3 py-4 text-bone">
      <div className="mx-auto max-w-7xl">
        <p className="text-eyebrow text-center text-rust text-xs">
          {competition.data?.name ?? 'Табло'}
        </p>

        <CategoryFilter
          categories={competition.data?.categories ?? []}
          value={selectedNames.size === 1 ? [...selectedNames][0] : null}
          onSelect={selectCategory}
        />

        {queue.isLoading && (
          <p className="mt-16 text-center text-lg text-steel-dim">Загрузка...</p>
        )}

        {tables.length > 0 && (
          <div className={`mt-4 grid ${gridClass} gap-3`}>
            {tables.map((table) => (
              <QueueBlock key={`${table.table_number}-${table.category_name}-${table.hand}`} table={table} tableCount={tables.length} />
            ))}
          </div>
        )}

        {tables.length === 0 && !queue.isLoading && (
          <p className="mt-16 text-center text-lg text-steel-dim">
            {selectedNames.size > 0 ? 'Нет столов' : 'Нет данных'}
          </p>
        )}
      </div>
    </div>
  )
}
