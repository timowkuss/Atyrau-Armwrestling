import { useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useCompetition, useCompetitionQueue } from '@/features/competitions/useCompetitions'
import type { TableQueueOut, QueuePairOut } from '@/types/api'

function autoFontSize(text: string, single = false): string {
  const len = text.length
  if (single) {
    if (len <= 14) return 'text-5xl sm:text-6xl md:text-7xl'
    if (len <= 20) return 'text-4xl sm:text-5xl md:text-6xl'
    if (len <= 28) return 'text-3xl sm:text-4xl md:text-5xl'
    if (len <= 36) return 'text-2xl sm:text-3xl md:text-4xl'
    return 'text-xl sm:text-2xl md:text-3xl'
  }
  if (len <= 12) return 'text-2xl sm:text-3xl'
  if (len <= 18) return 'text-xl sm:text-2xl'
  if (len <= 24) return 'text-lg sm:text-xl'
  if (len <= 32) return 'text-base sm:text-lg'
  return 'text-sm sm:text-base'
}

function PairBlock({ pair, label, single }: { pair: QueuePairOut; label?: string; single?: boolean }) {
  const p1Size = autoFontSize(pair.p1_name, single)
  const p2Size = autoFontSize(pair.p2_name, single)
  return (
    <div className="flex flex-col items-center gap-0.5">
      <p className={`font-display font-bold leading-tight text-bone ${p1Size}`}>
        {pair.p1_name}
      </p>
      <p className="font-mono text-xs text-steel">vs</p>
      <p className={`font-display font-bold leading-tight text-bone ${p2Size}`}>
        {pair.p2_name}
      </p>
      {label && <p className="text-[10px] uppercase tracking-widest text-emerald-400 mt-0.5">{label}</p>}
    </div>
  )
}

function CompletedBlock() {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <p className="font-mono text-[10px] uppercase tracking-wider text-steel-dim">Турнир завершён</p>
    </div>
  )
}

function QueueBlock({ table, single }: { table: TableQueueOut; single?: boolean }) {
  const hasMatch = !!table.current
  const hasStandings = table.eliminated.length > 0
  const categoryLabel = table.category_name.replace(/\s*Both\s*/i, '').trim()
  const handLabel = table.hand === 'left' ? 'Левая' : 'Правая'

  return (
    <div className={`flex flex-col border border-steel-dim/20 bg-black/20 ${single ? 'p-6 sm:p-10' : 'p-3 sm:p-4'}`}>
      <div className="text-center mb-3">
        <p className={`font-display font-bold uppercase tracking-[0.25em] text-emerald-400 ${single ? 'text-2xl sm:text-3xl' : 'text-lg sm:text-xl'}`}>
          Стол {table.table_number}
        </p>
        <p className={`font-mono text-steel-dim mt-0.5 ${single ? 'text-xs' : 'text-[10px]'}`}>
          {categoryLabel} | {handLabel} рука
        </p>
      </div>

      {hasMatch ? (
        <div className={`border-b border-steel-dim/10 ${single ? 'py-8' : 'py-3'}`}>
          <PairBlock pair={table.current!} label="сейчас" single={single} />
        </div>
      ) : hasStandings ? (
        <div className={`border-b border-steel-dim/10 ${single ? 'py-8' : 'py-3'}`}>
          <CompletedBlock />
        </div>
      ) : (
        <div className={`border-b border-steel-dim/10 ${single ? 'py-8' : 'py-3'}`}>
          <p className="text-center text-sm text-steel-dim">Ожидание</p>
        </div>
      )}

      {table.next.length > 0 && (
        <div className={`border-b border-steel-dim/10 space-y-3 ${single ? 'py-5' : 'py-2'}`}>
          {table.next.map((pair, i) => (
            <PairBlock key={pair.match_id} pair={pair} label={i === 0 ? 'далее' : undefined} single={single} />
          ))}
        </div>
      )}

      {hasStandings && (
        <div className={`space-y-0.5 ${single ? 'pt-4' : 'pt-2'}`}>
          {table.eliminated.map((e) => (
            <p key={e.athlete_name} className={`text-center font-mono text-steel-dim ${single ? 'text-sm' : 'text-[11px]'}`}>
              {e.place}. <span className="text-bone">{e.athlete_name}</span>
              {e.wins > 0 || e.losses > 0 ? (
                <span className="ml-1 text-steel-dim/50">
                  {e.wins}-{e.losses}
                </span>
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

  const clearFilter = () => {
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
          onClear={clearFilter}
        />

        {queue.isLoading && (
          <p className="mt-16 text-center text-lg text-steel-dim">Загрузка...</p>
        )}

        {tables.length > 0 && (
          <div className={`mt-4 grid ${gridClass} gap-3`}>
            {tables.map((table) => (
              <QueueBlock key={`${table.category_name}-${table.hand}`} table={table} single={tables.length === 1} />
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
