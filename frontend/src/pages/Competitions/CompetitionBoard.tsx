import { useParams } from 'react-router-dom'
import { useCompetition, useCompetitionQueue } from '@/features/competitions/useCompetitions'
import type { TableQueueOut, QueuePairOut } from '@/types/api'

function PairBlock({ pair, label }: { pair: QueuePairOut; label?: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <p className="font-mono text-xs text-steel">{pair.category_name}{pair.round_name ? ` · ${pair.round_name}` : ''}</p>
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
  return (
    <div className="flex flex-col rounded-[var(--radius-rivet)] border border-steel-dim/40 bg-black/30 p-8">
      <p className="text-center text-eyebrow text-2xl tracking-[0.3em] text-emerald-400">
        СТОЛ {table.table_number}
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
    </div>
  )
}

export function CompetitionBoard() {
  const { id } = useParams<{ id: string }>()
  const competitionId = Number(id)

  const competition = useCompetition(competitionId)
  const queue = useCompetitionQueue(competitionId)

  const tables = queue.data ?? []
  const cols = tables.length > 1 ? 'sm:grid-cols-2' : ''

  return (
    <div className="min-h-screen bg-ink px-6 py-8 text-bone">
      <div className="mx-auto max-w-6xl">
        <p className="text-eyebrow text-center text-rust">
          {competition.data?.name ?? 'Табло'}
        </p>

        {queue.isLoading && (
          <p className="mt-16 text-center text-2xl text-steel-dim">Загрузка...</p>
        )}

        {tables.length > 0 && (
          <div className={`mt-8 grid grid-cols-1 gap-6 ${cols}`}>
            {tables.map((table) => (
              <QueueBlock key={table.table_number} table={table} />
            ))}
          </div>
        )}

        {tables.length === 0 && !queue.isLoading && (
          <p className="mt-16 text-center text-2xl text-steel-dim">Нет данных</p>
        )}
      </div>
    </div>
  )
}
