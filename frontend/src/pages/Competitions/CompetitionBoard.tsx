import { useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useCompetition, useCompetitionQueue } from '@/features/competitions/useCompetitions'
import type { TableQueueOut, QueuePairOut } from '@/types/api'

function pairFontSize(totalLen: number, tableCount: number): string {
  const w = tableCount <= 1 ? totalLen : totalLen * (tableCount <= 2 ? 1.7 : tableCount <= 3 ? 2.2 : 2.8)
  if (w <= 14) return 'text-4xl sm:text-5xl md:text-6xl'
  if (w <= 20) return 'text-3xl sm:text-4xl md:text-5xl'
  if (w <= 28) return 'text-2xl sm:text-3xl md:text-4xl'
  if (w <= 36) return 'text-xl sm:text-2xl md:text-3xl'
  if (w <= 48) return 'text-base sm:text-lg md:text-xl'
  if (w <= 60) return 'text-sm sm:text-base md:text-lg'
  return 'text-xs sm:text-sm md:text-base'
}

function PairBlock({ pair, label, tableCount }: { pair: QueuePairOut; label?: string; tableCount: number }) {
  const totalLen = pair.p1_name.length + pair.p2_name.length
  const size = pairFontSize(totalLen, tableCount)
  return (
    <div className="flex flex-col items-center gap-0.5">
      {label && <p className="text-[10px] uppercase tracking-widest text-emerald-400">{label}</p>}
      <p className={`font-display font-bold leading-tight text-bone whitespace-nowrap ${size}`}>
        {pair.p1_name}
        <span className="mx-1.5 font-mono text-steel font-normal">vs</span>
        {pair.p2_name}
      </p>
    </div>
  )
}

function QueueBlock({ table, tableCount }: { table: TableQueueOut; tableCount: number }) {
  const hasMatch = !!table.current
  const hasStandings = table.eliminated.length > 0
  const isComplete = !hasMatch && hasStandings
  const categoryLabel = table.category_name.replace(/\s*Both\s*/i, '').trim()
  const handLabel = table.hand === 'left' ? 'Левая' : 'Правая'
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
          <PairBlock pair={table.current!} label="сейчас" tableCount={tableCount} />
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
        <div className={`border-b border-steel-dim/10 ${isSingle ? 'py-4 space-y-4' : 'py-2 space-y-2'}`}>
          {table.next.map((pair, i) => (
            <PairBlock key={pair.match_id} pair={pair} label={i === 0 ? 'далее' : undefined} tableCount={tableCount} />
          ))}
        </div>
      ) : hasMatch ? (
        <div className={`border-b border-steel-dim/10 ${isSingle ? 'py-4' : 'py-2'}`}>
          <p className="text-center text-sm text-steel-dim">Следующая пара не готова</p>
        </div>
      ) : null}

      {hasStandings && (
        <div className={`${isSingle ? 'pt-3 space-y-1' : 'pt-1.5 space-y-0.5'}`}>
          {table.eliminated.map((e) => (
              <p key={e.athlete_name} className={`text-left font-mono text-steel-dim ${isSingle ? 'text-sm' : 'text-[11px]'}`}>
              {e.place}. <span className="text-bone">{e.athlete_name}</span>
              {e.wins > 0 || e.losses > 0 ? (
                <span className="ml-1 text-steel-dim/50">{e.wins}-{e.losses}</span>
              ) : null}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

function CategoryFilter({
  categories,
  selected,
  onToggle,
  onClear,
}: {
  categories: { id: number; name: string }[]
  selected: Set<string>
  onToggle: (name: string) => void
  onClear: () => void
}) {
  if (categories.length === 0) return null

  return (
    <div className="mt-4 flex flex-wrap items-center justify-center gap-1.5">
      {categories.map((c) => {
        const active = selected.has(c.name)
        return (
          <button
            key={c.id}
            onClick={() => onToggle(c.name)}
            className={`rounded-full border px-2.5 py-0.5 font-mono text-[10px] transition-colors ${
              active
                ? 'border-emerald-400 bg-emerald-400/10 text-emerald-400'
                : 'border-steel-dim/30 text-steel-dim hover:text-steel'
            }`}
          >
            {c.name}
          </button>
        )
      })}
      {selected.size > 0 && (
        <button
          onClick={onClear}
          className="rounded-full border border-steel-dim/30 px-2.5 py-0.5 font-mono text-[10px] text-steel-dim hover:text-steel"
        >
          все
        </button>
      )}
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

  const toggleCategory = (name: string) => {
    const next = new Set(selectedNames)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    const params = new URLSearchParams(searchParams)
    if (next.size === 0) params.delete('categories')
    else params.set('categories', [...next].map(encodeURIComponent).join(','))
    setSearchParams(params, { replace: true })
  }

  const clearCategories = () => {
    const params = new URLSearchParams(searchParams)
    params.delete('categories')
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
          selected={selectedNames}
          onToggle={toggleCategory}
          onClear={clearCategories}
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
