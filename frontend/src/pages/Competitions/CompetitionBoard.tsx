import { useParams } from 'react-router-dom'
import { useCompetition, useCompetitionQueue } from '@/features/competitions/useCompetitions'
import type { TableQueueOut } from '@/types/api'

function TableBlock({ table }: { table: TableQueueOut }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-[var(--radius-rivet)] border border-steel-dim/40 bg-black/30 px-8 py-10 text-center">
      <p className="text-eyebrow text-2xl tracking-[0.3em] text-emerald-400">
        СТОЛ {table.table_number}
      </p>

      {table.current ? (
        <>
          <p className="font-mono text-lg text-steel">
            {table.current.category_name}
            {table.current.round_name ? ` · ${table.current.round_name}` : ''}
          </p>
          <p className="font-display text-4xl font-bold leading-tight text-bone sm:text-5xl">
            {table.current.p1_name}
            <span className="mx-3 text-steel">vs</span>
            {table.current.p2_name}
          </p>
        </>
      ) : (
        <p className="text-2xl text-steel-dim">Нет активного поединка</p>
      )}

      {table.next.length > 0 && (
        <div className="mt-6 w-full border-t border-steel-dim/30 pt-5">
          <p className="text-eyebrow text-lg text-brass">Следующий бой</p>
          <p className="mt-2 text-2xl text-bone">
            {table.next[0].p1_name} <span className="text-steel">vs</span> {table.next[0].p2_name}
          </p>
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

        {tables.length > 0 ? (
          <div className={`mt-8 grid grid-cols-1 gap-6 ${cols}`}>
            {tables.map((table) => (
              <TableBlock key={table.table_number} table={table} />
            ))}
          </div>
        ) : (
          <p className="mt-16 text-center text-2xl text-steel-dim">Нет активных столов</p>
        )}
      </div>
    </div>
  )
}
