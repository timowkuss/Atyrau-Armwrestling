import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCompetition, useCompetitionBracket, useCompetitionHandResults, useCompetitionParticipants, useCompetitionResults } from '@/features/competitions/useCompetitions'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { MedalBadge } from '@/components/ui/Medal'
import { BracketTree } from '@/components/ui/BracketBoard'
import type { BracketMatchOut, CategoryOut, CompetitionStatus, HandResultOut, ParticipantOut, ResultOut } from '@/types/api'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })
}

function formatLabel(c: {
  format_type: 'combined' | 'separate' | null
  bracket_system: 'double' | 'single' | null
  weight_tolerance: number | null
}) {
  const parts: string[] = []
  if (c.format_type) {
    parts.push(c.format_type === 'combined' ? 'Двоеборье' : 'По одной руке')
  }
  if (c.bracket_system) {
    parts.push(c.bracket_system === 'single' ? 'До одного поражения' : 'До двух поражений')
  }
  if (c.weight_tolerance != null) {
    parts.push(`Допуск по весу ${c.weight_tolerance} кг`)
  }
  return parts
}

function statusBadge(status: CompetitionStatus) {
  const map: Record<CompetitionStatus, { label: string; cls: string }> = {
    draft:        { label: 'черновик',  cls: 'bg-steel-dim/30 text-steel-dim' },
    published:    { label: 'скоро',     cls: 'bg-brass/15 text-brass' },
    in_progress:  { label: 'идёт',     cls: 'bg-emerald-500/20 text-emerald-400' },
    completed:    { label: 'завершён',  cls: 'bg-rust/15 text-rust' },
  }
  const b = map[status]
  return (
    <span className={`text-eyebrow rounded-[var(--radius-rivet)] px-2.5 py-0.5 ${b.cls}`}>
      {b.label}
    </span>
  )
}

// Руки на бэкенде хранятся по-русски («Обе», «Левая», «Правая»), но для
// совместимости со старыми данными поддерживаем и английские варианты.
function handLabel(hand: string): string {
  switch (hand) {
    case 'Обе': case 'Both': case 'both': return 'Двоеборье'
    case 'Левая': case 'left': return 'Левая'
    case 'Правая': case 'right': return 'Правая'
    default: return hand
  }
}

// Название категории без суффикса "Both" (он дублируется меткой руки).
function cleanCategoryName(name: string): string {
  const cleaned = name.replace(/\s*Both\b/gi, '').trim()
  return cleaned || name
}

function ParticipantList({ participants }: { participants: ParticipantOut[] }) {
  if (participants.length === 0) return null

  const byCategory = participants.reduce<Record<string, ParticipantOut[]>>((acc, p) => {
    ;(acc[p.category_name] ??= []).push(p)
    return acc
  }, {})

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {Object.entries(byCategory).map(([category, members]) => (
        <div key={category} className="plate rounded-[var(--radius-rivet)] p-5">
          <div className="flex items-center justify-between">
            <h3 className="font-display text-sm text-brass">{category}</h3>
            <span className="text-eyebrow text-steel">{members.length}</span>
          </div>
          <ol className="mt-3 space-y-1.5">
            {members.map((m, i) => (
              <li key={m.athlete_id} className="flex items-baseline gap-2 text-sm">
                <span className="w-5 shrink-0 text-right font-mono text-steel-dim">{i + 1}.</span>
                <Link to={`/athletes/${m.athlete_id}`} className="min-w-0 flex-1 truncate text-bone hover:text-brass">
                  {m.athlete_name}
                </Link>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}

function ResultsTable({ rows }: { rows: ResultOut[] }) {
  if (rows.length === 0) return null
  return (
    <div className="overflow-x-auto">
      <table className="mt-2 w-full min-w-[300px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-steel-dim/30 text-eyebrow uppercase tracking-widest text-steel-dim">
            <th className="py-2 pr-4 font-medium">Место</th>
            <th className="py-2 pr-4 font-medium">Участник</th>
            <th className="hidden py-2 pr-4 font-medium sm:table-cell">Клуб</th>
            <th className="py-2 font-medium">Награда</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-steel-dim/15">
              <td className="py-2 pr-4 font-mono text-bone">{r.place ?? '—'}</td>
              <td className="py-2 pr-4">
                <Link to={`/athletes/${r.athlete_id}`} className="whitespace-nowrap text-bone hover:text-brass">
                  {r.athlete_name}
                </Link>
              </td>
              <td className="hidden py-2 pr-4 text-steel sm:table-cell">{r.club_name ?? '—'}</td>
              <td className="py-2">
                <MedalBadge medal={r.medal} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Результаты отдельной руки (левая/правая) — по месту без награды: медали
// в протоколе висят только за итог категории (двоеборье), не за руку.
function HandResultsTable({ rows }: { rows: HandResultOut[] }) {
  if (rows.length === 0) {
    return <p className="mt-3 text-sm text-steel">Результаты по этой руке не найдены.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="mt-2 w-full min-w-[300px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-steel-dim/30 text-eyebrow uppercase tracking-widest text-steel-dim">
            <th className="py-2 pr-4 font-medium">Место</th>
            <th className="py-2 pr-4 font-medium">Участник</th>
            <th className="hidden py-2 pr-4 font-medium sm:table-cell">Клуб</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-steel-dim/15">
              <td className="py-2 pr-4 font-mono text-bone">{r.place}</td>
              <td className="py-2 pr-4">
                <Link to={`/athletes/${r.athlete_id}`} className="whitespace-nowrap text-bone hover:text-brass">
                  {r.athlete_name}
                </Link>
              </td>
              <td className="hidden py-2 pr-4 text-steel sm:table-cell">{r.club_name ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function groupByHand(matches: BracketMatchOut[]): Record<string, BracketMatchOut[]> {
  return matches.reduce<Record<string, BracketMatchOut[]>>((acc, m) => {
    ;(acc[m.hand] ??= []).push(m)
    return acc
  }, {})
}

// Есть ли в руке хоть один сыгранный матч (done/bye). Руки, где ничего не
// сыграно (все матчи pending/waiting), — "неверные данные": например, в
// завершённом двоеборье правая рука могла не разыгрываться, и показывать
// её пустую сетку не нужно.
function hasPlayedMatches(matches: BracketMatchOut[]): boolean {
  return matches.some((m) => m.status === 'done' || m.status === 'bye')
}

// Сетка выбранной категории. Для двоеборья (hand == "Обе") — переключатель
// «Левая рука»/«Правая рука» (карусель): выбранная рука показывает свою сетку
// и свой результат. Показываем только сыгранные руки (рука, которая вообще не
// разыгрывалась в завершённом турнире, — "неверные данные", её не рисуем).
// Внизу отдельный блок итогов: для двоеборья это ИТОГ по сумме обеих рук.
function CategoryBracketSection({
  category,
  matches,
  results,
  handResults,
}: {
  category: CategoryOut
  matches: BracketMatchOut[]
  results: ResultOut[] | undefined
  handResults: HandResultOut[] | undefined
}) {
  const catMatches = matches.filter((m) => m.category_name === category.name)
  const byHand = groupByHand(catMatches)
  const isCombined = category.hand === 'Обе' || category.hand === 'Both'

  const order = ['Левая', 'Правая']
  const hands = isCombined
    ? order.filter((h) => byHand[h] && hasPlayedMatches(byHand[h]))
    : Object.keys(byHand).filter((h) => h === category.hand || hasPlayedMatches(byHand[h]))

  const [activeHand, setActiveHand] = useState<string | null>(null)
  const currentHand = activeHand && hands.includes(activeHand) ? activeHand : (hands[0] ?? null)

  if (hands.length === 0 || !currentHand) {
    return <EmptyState title="Сетка по этой категории не найдена" />
  }

  const handResultRows = (handResults ?? []).filter(
    (r) => r.category_id === category.id && r.hand === currentHand,
  )

  const switchButtonCls = (active: boolean) =>
    active
      ? 'rounded-lg border border-brass bg-brass/15 px-4 py-2 font-mono text-xs font-medium uppercase tracking-widest text-brass'
      : 'rounded-lg border border-steel-dim/40 px-4 py-2 font-mono text-xs font-medium uppercase tracking-widest text-steel hover:border-steel-dim hover:text-bone'

  return (
    <div className="space-y-10">
      <div>
        {hands.length > 1 && (
          <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Рука">
            {hands.map((hand) => (
              <button
                key={hand}
                type="button"
                role="tab"
                aria-selected={hand === currentHand}
                onClick={() => setActiveHand(hand)}
                className={switchButtonCls(hand === currentHand)}
              >
                {handLabel(hand)} рука
              </button>
            ))}
          </div>
        )}
        <div>
          <BracketTree matches={byHand[currentHand]} />
        </div>
        <h3 className="mt-8 border-b border-steel-dim/20 pb-2 font-display text-sm text-bone">
          Результат · {handLabel(currentHand)} рука
        </h3>
        <HandResultsTable rows={handResultRows} />
      </div>

      {isCombined && results && results.length > 0 && (
        <div>
          <h3 className="border-b border-steel-dim/20 pb-2 font-display text-sm text-bone">
            ИТОГ · Двоеборье
          </h3>
          <ResultsTable rows={results} />
        </div>
      )}
    </div>
  )
}

export function CompetitionDetail() {
  const { id } = useParams<{ id: string }>()
  const competitionId = Number(id)

  const competition = useCompetition(competitionId)
  const results = useCompetitionResults(competitionId)
  const handResults = useCompetitionHandResults(competitionId)
  const participants = useCompetitionParticipants(competitionId)
  const bracket = useCompetitionBracket(competitionId)

  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null)
  useEffect(() => setSelectedCategoryId(null), [competitionId])

  if (competition.isLoading) return <LoadingState label="Загрузка турнира" />
  if (competition.isError) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <ErrorState
          title="Турнир не найден"
          message={(competition.error as Error).message}
          onRetry={() => competition.refetch()}
        />
      </div>
    )
  }
  if (!competition.data) return null

  const c = competition.data
  const isFinished = c.status === 'completed'
  const isLive = c.status === 'in_progress'
  const selectedCategory = c.categories.find((cat) => cat.id === selectedCategoryId) ?? c.categories[0]
  const resultsByCategory = (results.data ?? []).reduce<Record<string, ResultOut[]>>((acc, r) => {
    ;(acc[r.category_name] ??= []).push(r)
    return acc
  }, {})

  return (
    <div className="mx-auto max-w-4xl px-5 py-12">
      <Link to="/competitions" className="text-sm text-steel hover:text-brass">
        ← ко всем турнирам
      </Link>

      <div className="plate mt-4 rounded-[var(--radius-rivet)] p-6">
        <div className="flex flex-wrap items-center justify-between gap-y-2 gap-x-3">
          <p className="text-eyebrow text-rust">{formatDate(c.date)}</p>
          <div className="flex flex-wrap items-center gap-3">
            {statusBadge(c.status)}
            {isLive && (
              <a
                href={`/competitions/${competitionId}/board`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-eyebrow rounded-[var(--radius-rivet)] border border-brass/40 bg-brass/10 px-3 py-1.5 text-brass hover:bg-brass/20"
              >
                📺 Табло
              </a>
            )}
          </div>
        </div>
        <h1 className="mt-2 font-display text-2xl text-bone sm:text-3xl">{c.name}</h1>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-sm text-steel">
          {c.location_city_name && <span>{c.location_city_name}</span>}
          <span>{c.organizer ?? 'Федерация армрестлинга Атырау'}</span>
          <span>{c.participants_count} участников</span>
        </div>
        {formatLabel(c).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-steel-dim">
            {formatLabel(c).map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
        )}
        {c.description && <p className="mt-4 max-w-2xl break-words text-sm text-steel">{c.description}</p>}
        {c.categories.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {c.categories.map((cat) => (
              <span
                key={cat.id}
                className="text-eyebrow rounded-[var(--radius-rivet)] border border-steel-dim px-2 py-1 text-steel"
              >
                {cleanCategoryName(cat.name)} · {handLabel(cat.hand)}
              </span>
            ))}
          </div>
        )}
      </div>

      {participants.data && participants.data.length > 0 && (
        <section className="mt-10">
          <h2 className="font-display text-xl text-bone">Участники</h2>
          <div className="rivet-line my-4" />
          <ParticipantList participants={participants.data} />
        </section>
      )}

      <section className="mt-10 mb-16">
        <h2 className="font-display text-xl text-bone">Турнирная сетка</h2>
        <div className="rivet-line my-4" />
        {!isFinished ? (
          <EmptyState title="Турнир ещё не завершён" />
        ) : (
          <>
            {c.categories.length > 1 && (
              <div className="mb-6 flex max-w-sm flex-col gap-1.5">
                <label htmlFor="bracket-category" className="font-mono text-[11px] font-medium uppercase tracking-widest text-steel-dim">
                  Категория
                </label>
                <select
                  id="bracket-category"
                  value={selectedCategory.id}
                  onChange={(e) => setSelectedCategoryId(Number(e.target.value))}
                  className="w-full rounded-lg border border-steel-dim/20 bg-ink/80 px-3.5 py-2.5 text-sm text-bone backdrop-blur transition-colors focus:border-brass/50 focus:bg-ink focus:outline-none"
                >
                  {c.categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cleanCategoryName(cat.name)} · {handLabel(cat.hand)}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {bracket.isLoading ? (
              <LoadingState label="Загрузка сетки" />
            ) : bracket.data && bracket.data.length > 0 ? (
              <CategoryBracketSection
                key={selectedCategory.id}
                category={selectedCategory}
                matches={bracket.data}
                results={resultsByCategory[selectedCategory.name]}
                handResults={handResults.data}
              />
            ) : (
              <EmptyState title="Сетка не найдена" />
            )}
          </>
        )}
      </section>
    </div>
  )
}
