import type { QueuePairOut, TableQueueOut } from '@/types/api'

function tabloRoundName(roundName: string | null): string | null {
  if (!roundName) return null
  if (roundName.includes('переигровка')) return 'Суперфинал (переигровка)'
  if (roundName.includes('Гранд-финал') || roundName.includes('Финал')) return 'Финал'
  if (roundName.includes('1/2') || roundName.includes('Раунд')) return 'Полуфинал'
  return null
}

function PairLine({ pair }: { pair: QueuePairOut }) {
  return (
    <p className="truncate">
      {pair.p1_name} <span className="text-steel">vs</span> {pair.p2_name}
    </p>
  )
}

function TableCard({ table }: { table: TableQueueOut }) {
  return (
    <div className="plate rounded-[var(--radius-rivet)] p-5">
      <p className="text-eyebrow text-rust">Стол {table.table_number}</p>

      {table.current ? (
        <div className="mt-3">
          <p className="text-eyebrow text-brass">Сейчас борются</p>
          <p className="mt-1 text-lg text-bone">
            {table.current.p1_name} <span className="text-steel">vs</span> {table.current.p2_name}
          </p>
          <p className="mt-1 font-mono text-xs text-steel">
            {table.current.category_name} · {table.current.hand}
            {tabloRoundName(table.current.round_name) ? ` · ${tabloRoundName(table.current.round_name)}` : ''}
          </p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-steel">Нет активного поединка</p>
      )}

      {table.next.length > 0 && (
        <div className="mt-4 border-t border-steel-dim/20 pt-3">
          <p className="text-eyebrow text-steel">Следующие пары</p>
          <div className="mt-2 space-y-1.5 text-sm text-bone">
            {table.next.map((pair) => (
              <PairLine key={pair.match_id} pair={pair} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function LiveQueueBoard({ tables }: { tables: TableQueueOut[] }) {
  if (tables.length === 0) return null

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {tables.map((table) => (
        <TableCard key={table.table_number} table={table} />
      ))}
    </div>
  )
}
