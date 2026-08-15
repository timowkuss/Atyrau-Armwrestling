import { useEffect, useMemo, useRef, useState } from 'react'
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

function FighterChip({ name, photo, compact, reverse }: { name: string; photo: string | null; compact?: boolean; reverse?: boolean }) {
  const src = cloudinaryThumb(photo, compact ? 96 : 192)
  return (
    <div className={`flex min-w-0 items-center gap-1.5 sm:gap-2 ${reverse ? 'flex-col sm:flex-row-reverse' : 'flex-col sm:flex-row'}`}>
      <div
        className={`shrink-0 overflow-hidden bg-gray-200 ring-1 ring-gray-300 ${
          compact ? 'h-10 w-10 rounded-lg sm:h-12 sm:w-12' : 'h-16 w-16 rounded-xl sm:h-28 sm:w-28'
        }`}
      >
        {src ? (
          <img src={src} alt={name} className="h-full w-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <span className={`flex h-full w-full items-center justify-center font-mono text-gray-600 ${compact ? 'text-sm sm:text-base' : 'text-lg sm:text-4xl'}`}>
            {initials(name)}
          </span>
        )}
      </div>
      <span
        className={`min-w-0 break-words text-center leading-tight text-gray-900 sm:truncate sm:text-left ${
          compact ? 'text-xs sm:text-sm' : 'text-sm sm:text-xl'
        }`}
      >
        {name}
      </span>
    </div>
  )
}

function PairBlock({ pair, label, compact }: { pair: QueuePairOut; label?: string; compact?: boolean }) {
  const displayRound = tabloRoundName(pair.round_name)
  return (
    <div className="flex flex-col items-center gap-0.5">
      {label && <p className="text-[10px] uppercase tracking-widest text-emerald-600">{label}</p>}
      {displayRound && (
        <p className="font-mono text-[9px] uppercase tracking-wider text-amber-700">{displayRound}</p>
      )}
      <div className="flex w-full items-center justify-center gap-2 sm:gap-6">
        <div className={`${compact ? 'max-w-[40%] sm:max-w-[42%]' : 'max-w-[40%] sm:max-w-[44%]'}`}>
          <FighterChip name={pair.p1_name} photo={pair.p1_photo} compact={compact} />
        </div>
        <span className={`font-mono shrink-0 text-gray-400 font-normal ${compact ? 'text-sm' : 'text-xl sm:text-3xl'}`}>vs</span>
        <div className={`${compact ? 'max-w-[40%] sm:max-w-[42%]' : 'max-w-[40%] sm:max-w-[44%]'}`}>
          <FighterChip name={pair.p2_name} photo={pair.p2_photo} compact={compact} reverse />
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
    <div className={`flex flex-col border border-gray-200 bg-gray-50 ${isSingle ? 'p-6 sm:p-10' : 'p-3 sm:p-4'}`}>
      <div className="text-center mb-2">
        {isComplete ? (
          <p className={`font-display font-bold uppercase tracking-[0.25em] text-emerald-600 ${isSingle ? 'text-2xl sm:text-3xl' : 'text-lg sm:text-xl'}`}>
            {categoryLabel} <span className="text-gray-400">|</span> {handLabel}
          </p>
        ) : (
          <>
            <p className={`font-display font-bold uppercase tracking-[0.25em] text-emerald-600 ${isSingle ? 'text-2xl sm:text-3xl' : 'text-lg sm:text-xl'}`}>
              Стол {table.table_number}
            </p>
            <p className="font-mono text-xs sm:text-sm text-gray-600 mt-0.5">
              {categoryLabel} | {handLabel} рука
            </p>
          </>
        )}
      </div>

      {hasMatch ? (
        <div className={`border-b border-gray-200 ${isSingle ? 'py-6' : 'py-2'}`}>
          <PairBlock pair={table.current!} label="сейчас" />
        </div>
      ) : isComplete ? (
        <div className={`border-b border-gray-200 ${isSingle ? 'py-6' : 'py-2'}`}>
          <p className="text-center font-mono text-[10px] uppercase tracking-wider text-gray-400">Турнир завершён</p>
        </div>
      ) : (
        <div className={`border-b border-gray-200 ${isSingle ? 'py-6' : 'py-2'}`}>
          <p className="text-center text-sm text-gray-400">Ожидание</p>
        </div>
      )}

      {table.next.length > 0 ? (
        <div className={`border-b border-gray-200 ${isSingle ? 'py-4 space-y-3' : 'py-2 space-y-2'}`}>
          {table.next.map((pair, i) => (
            <PairBlock key={pair.match_id} pair={pair} label={i === 0 ? 'далее' : undefined} compact />
          ))}
        </div>
      ) : hasMatch ? (
        <div className={`border-b border-gray-200 ${isSingle ? 'py-4' : 'py-2'}`}>
          <p className="text-center text-sm text-gray-400">Следующая пара не готова</p>
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
              <p key={e.athlete_name} className={`flex items-center gap-1.5 text-left font-mono text-gray-500 ${elimSize}`}>
                <span className="inline-block w-5 shrink-0 text-right">{e.place}.</span>
                <span className="min-w-0 flex-1 truncate text-gray-900">{e.athlete_name}</span>
                {e.wins > 0 || e.losses > 0 ? (
                  <span className="ml-1 shrink-0 text-gray-400">{e.wins}-{e.losses}</span>
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
  selected,
  onToggle,
  onSelectAll,
}: {
  categories: { id: number; name: string }[]
  selected: Set<string>
  onToggle: (name: string) => void
  onSelectAll: (select: boolean) => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (categories.length === 0) return null

  const allSelected = categories.every((c) => selected.has(c.name))
  const someSelected = categories.some((c) => selected.has(c.name))
  const label = !someSelected
    ? 'Все категории'
    : selected.size === 1
      ? [...selected][0]
      : `Выбрано: ${selected.size}`

  return (
    <div ref={rootRef} className="relative mt-4 flex justify-center">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 font-mono text-sm text-gray-900 transition-colors hover:border-gray-400 focus:border-emerald-500 focus:outline-none"
      >
        <span className="max-w-56 truncate">{label}</span>
        <span className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
      </button>

      {open && (
        <div className="absolute left-1/2 top-full z-20 mt-1.5 w-72 max-w-[calc(100vw-2rem)] -translate-x-1/2 rounded-md border border-gray-200 bg-white shadow-xl shadow-gray-200/50">
          <button
            onClick={() => onSelectAll(!allSelected)}
            className="flex w-full items-center gap-2 px-3 py-2 font-mono text-xs text-gray-500 transition-colors hover:bg-gray-50"
          >
            <span className={`flex h-4 w-4 items-center justify-center rounded border ${allSelected ? 'border-emerald-500 bg-emerald-500/20' : 'border-gray-300'}`}>
              {allSelected && <span className="text-[10px] text-emerald-600">✓</span>}
            </span>
            {allSelected ? 'Снять все' : 'Выбрать все'}
          </button>
          <div className="h-px bg-gray-100" />
          <div className="max-h-64 overflow-y-auto py-1">
            {categories.map((c) => {
              const active = selected.has(c.name)
              return (
                <button
                  key={c.id}
                  onClick={() => onToggle(c.name)}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-gray-900 transition-colors hover:bg-gray-50"
                >
                  <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${active ? 'border-emerald-500 bg-emerald-500/20' : 'border-gray-300'}`}>
                    {active && <span className="text-[10px] text-emerald-600">✓</span>}
                  </span>
                  <span className="truncate">{c.name}</span>
                </button>
              )
            })}
          </div>
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

  const selectAllCategories = (select: boolean) => {
    const params = new URLSearchParams(searchParams)
    if (select) params.set('categories', competition.data?.categories.map((c) => encodeURIComponent(c.name)).join(',') ?? '')
    else params.delete('categories')
    setSearchParams(params, { replace: true })
  }

  const tables = useMemo(() => {
    const allTables = queue.data ?? []
    if (selectedNames.size === 0) return allTables
    return allTables.filter((table) => selectedNames.has(table.category_name))
  }, [queue.data, selectedNames])

  const gridClass = tables.length <= 1
    ? 'grid-cols-1'
    : tables.length === 2
      ? 'grid-cols-1 sm:grid-cols-2'
      : tables.length <= 4
        ? 'grid-cols-1 sm:grid-cols-2'
        : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'

  return (
    <div className="min-h-screen bg-white px-3 py-4 text-gray-900">
      <div className="mx-auto max-w-7xl">
        <p className="text-center text-xs font-semibold uppercase tracking-widest text-amber-700">
          {competition.data?.name ?? 'Табло'}
        </p>

        <CategoryFilter
          categories={competition.data?.categories ?? []}
          selected={selectedNames}
          onToggle={toggleCategory}
          onSelectAll={selectAllCategories}
        />

        {queue.isLoading && (
          <p className="mt-16 text-center text-lg text-gray-400">Загрузка...</p>
        )}

        {competition.isError && (
          <p className="mt-16 text-center text-lg text-red-600">
            Ошибка загрузки турнира. Проверьте соединение и обновите страницу.
          </p>
        )}

        {!competition.isError && queue.isError && (
          <p className="mt-16 text-center text-lg text-red-600">
            Не удалось получить очередь столов. Сервер недоступен — проверьте
            соединение, данные обновятся автоматически.
          </p>
        )}

        {!competition.isError && !queue.isError && tables.length > 0 && (
          <div className={`mt-4 grid ${gridClass} gap-3`}>
            {tables.map((table) => (
              <QueueBlock key={`${table.table_number}-${table.category_name}-${table.hand}`} table={table} tableCount={tables.length} />
            ))}
          </div>
        )}

        {!competition.isError && !queue.isError && tables.length === 0 && !queue.isLoading && (
          <p className="mt-16 text-center text-lg text-gray-400">
            {selectedNames.size > 0 ? 'Нет столов' : 'Нет данных'}
          </p>
        )}
      </div>
      <p className="mt-8 text-center font-mono text-[9px] text-gray-300">build 2026-08-07</p>
    </div>
  )
}
