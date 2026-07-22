import { useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useCompetition, useCompetitionQueue } from '@/features/competitions/useCompetitions'
import type { TableQueueOut, QueuePairOut } from '@/types/api'

function autoFontSize(text: string): string {
  const len = text.length
  if (len <= 12) return 'text-4xl sm:text-5xl'
  if (len <= 18) return 'text-3xl sm:text-4xl'
  if (len <= 24) return 'text-2xl sm:text-3xl'
  if (len <= 32) return 'text-xl sm:text-2xl'
  return 'text-lg sm:text-xl'
}

function PairBlock({ pair, label }: { pair: QueuePairOut; label?: string }) {
  const p1Size = autoFontSize(pair.p1_name)
  const p2Size = autoFontSize(pair.p2_name)
  const roundLine = pair.round_name
    ? `${pair.hand === 'left' ? 'Л' : 'Правая'} · ${pair.round_name}`
    : pair.hand === 'left' ? 'Левая' : 'Правая'
  return (
    <div className="flex flex-col items-center gap-0.5">
      <p className="font-mono text-[10px] uppercase tracking-wider text-steel-dim">{roundLine}</p>
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

function QueueBlock({ table }: { table: TableQueueOut }) {
  const hasMatch = !!table.current
  const hasStandings = table.eliminated.length > 0

  return (
    <div className="flex flex-col border border-steel-dim/20 bg-black/20 p-3 sm:p-4">
      <div className="text-center mb-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-emerald-400">
          Стол {table.table_number}
        </p>
      </div>

      {hasMatch ? (
        <div className="py-3 border-b border-steel-dim/10">
          <PairBlock pair={table.current!} label="сейчас" />
        </div>
      ) : hasStandings ? (
        <div className="py-3 border-b border-steel-dim/10">
          <CompletedBlock />
        </div>
      ) : (
        <div className="py-3 border-b border-steel-dim/10">
          <p className="text-center text-sm text-steel-dim">Ожидание</p>
        </div>
      )}

      {table.next.length > 0 && (
        <div className="py-2 border-b border-steel-dim/10 space-y-3">
          {table.next.map((pair, i) => (
            <PairBlock key={pair.match_id} pair={pair} label={i === 0 ? 'далее' : undefined} />
          ))}
        </div>
      )}

      {hasStandings && (
        <div className="pt-2 space-y-0.5">
          {table.eliminated.map((e) => (
            <p key={e.athlete_name} className="text-center font-mono text-[11px] text-steel-dim">
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
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {tables.map((table) => (
              <QueueBlock key={`${table.category_name}-${table.hand}`} table={table} />
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
