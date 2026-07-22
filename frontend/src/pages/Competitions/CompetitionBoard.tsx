import { useMemo } from 'react' // eliminated tablo
import { useParams, useSearchParams } from 'react-router-dom'
import { useCompetition, useCompetitionQueue } from '@/features/competitions/useCompetitions'
import type { TableQueueOut, QueuePairOut } from '@/types/api'

function PairBlock({ pair, label }: { pair: QueuePairOut; label?: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <p className="font-mono text-xs text-steel">{pair.category_name} · {pair.hand}{pair.round_name ? ` · ${pair.round_name}` : ''}</p>
      <p className="font-display text-3xl font-bold leading-tight text-bone sm:text-4xl">
        {pair.p1_name}
        <span className="mx-2 text-steel">vs</span>
        {pair.p2_name}
      </p>
      {label && <p className="text-eyebrow text-xs text-emerald-400">{label}</p>}
    </div>
  )
}

function QueueBlock({ table }: { table: TableQueueOut }) {
  const handLabel = table.hand === 'left' ? 'Левая' : table.hand === 'right' ? 'Правая' : table.hand
  return (
    <div className="flex flex-col rounded-[var(--radius-rivet)] border border-steel-dim/40 bg-black/30 p-8">
      <p className="text-center text-eyebrow text-2xl tracking-[0.3em] text-emerald-400">
        СТОЛ {table.table_number}
      </p>
      <p className="text-center font-mono text-sm text-steel mt-1">
        {table.category_name} · {handLabel} рука
      </p>

      {table.current ? (
        <div className="mt-6 flex flex-col items-center gap-2 border-b border-steel-dim/20 pb-6">
          <PairBlock pair={table.current} label="сейчас" />
        </div>
      ) : (
        <div className="mt-6 flex flex-col items-center gap-2 border-b border-steel-dim/20 pb-6">
          <p className="text-xl text-steel-dim">Нет активного поединка</p>
        </div>
      )}

      {table.next.length > 0 && (
        <div className="mt-5 space-y-4">
          {table.next.map((pair, i) => (
            <PairBlock key={pair.match_id} pair={pair} label={i === 0 ? 'далее' : undefined} />
          ))}
        </div>
      )}

      {table.eliminated.length > 0 && (
        <div className="mt-6 border-t border-steel-dim/20 pt-5">
          <p className="text-eyebrow text-center text-sm text-rust mb-3">Таблица</p>
          <div className="space-y-1.5">
            {table.eliminated.map((e) => (
              <p key={e.athlete_name} className="text-center font-mono text-sm text-steel-dim">
                {e.place}. {e.athlete_name}
                <span className="ml-2 text-steel-dim/60">
                  {e.wins} побед{e.losses > 0 ? `, ${e.losses} ${e.losses === 1 ? 'поражение' : 'поражения'}` : ''}
                </span>
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Табло по умолчанию показывает столы со всеми категориями турнира сразу.
// Если нужно вывести на конкретный экран/проектор только часть категорий —
// отметьте их в списке ниже. Выбор сохраняется в ссылке (?categories=...),
// поэтому можно открыть /board с разным набором категорий на разных
// экранах одновременно и просто сохранить/расшарить готовую ссылку.
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
    <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
      {categories.map((c) => {
        const active = selected.has(c.name)
        return (
          <button
            key={c.id}
            onClick={() => onToggle(c.name)}
            className={`rounded-full border px-3 py-1 font-mono text-xs transition-colors ${
              active
                ? 'border-emerald-400 bg-emerald-400/10 text-emerald-400'
                : 'border-steel-dim/40 text-steel-dim hover:text-steel'
            }`}
          >
            {c.name}
          </button>
        )
      })}
      {selected.size > 0 && (
        <button
          onClick={onClear}
          className="rounded-full border border-steel-dim/40 px-3 py-1 font-mono text-xs text-steel-dim hover:text-steel"
        >
          Сбросить (показать все)
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

  // Ничего не выбрано — показываем всё как есть, без фильтрации.
  const tables = useMemo(() => {
    if (selectedNames.size === 0) return allTables

    return allTables.filter((table) => selectedNames.has(table.category_name))
  }, [allTables, selectedNames])

  const cols = tables.length > 1 ? 'sm:grid-cols-2' : ''

  return (
    <div className="min-h-screen bg-ink px-6 py-8 text-bone">
      <div className="mx-auto max-w-6xl">
        <p className="text-eyebrow text-center text-rust">
          {competition.data?.name ?? 'Табло'}
        </p>

        <CategoryFilter
          categories={competition.data?.categories ?? []}
          selected={selectedNames}
          onToggle={toggleCategory}
          onClear={clearFilter}
        />

        {queue.isLoading && (
          <p className="mt-16 text-center text-2xl text-steel-dim">Загрузка...</p>
        )}

        {tables.length > 0 && (
          <div className={`mt-8 grid grid-cols-1 gap-6 ${cols}`}>
            {tables.map((table) => (
              <QueueBlock key={`${table.category_name}-${table.hand}`} table={table} />
            ))}
          </div>
        )}

        {tables.length === 0 && !queue.isLoading && (
          <p className="mt-16 text-center text-2xl text-steel-dim">
            {selectedNames.size > 0 ? 'Нет активных столов по выбранным категориям' : 'Нет данных'}
          </p>
        )}
      </div>
    </div>
  )
}
