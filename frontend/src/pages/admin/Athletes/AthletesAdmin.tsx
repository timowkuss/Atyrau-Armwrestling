import { useState } from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import { useAdminClubsList } from '@/features/admin/useClubsAdmin'
import { useAdminCoachesList } from '@/features/admin/useCoachesAdmin'
import { useCities } from '@/features/useCities'
import {
  useAdminAthleteStatistics,
  useAdminAthletes,
  useCreateAthlete,
  useDeleteAthlete,
  useRecalculateAthleteStatistics,
  useUpdateAthlete,
  useUpdateAthleteStatistics,
} from '@/features/admin/useAthletesAdmin'
import { LoadingState, ErrorState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import type { AthleteInput, AthleteStatisticsUpdateInput, Gender } from '@/types/api'

const EMPTY_FORM: AthleteInput = { full_name: '', gender: 'male' }

export function AthletesAdmin() {
  const { user } = useAuth()
  const canDelete = user?.role_code === 'super_admin'

  const [search, setSearch] = useState('')
  const athletes = useAdminAthletes(search || undefined)
  const clubs = useAdminClubsList()
  const coaches = useAdminCoachesList()
  const cities = useCities()

  const createAthlete = useCreateAthlete()
  const updateAthlete = useUpdateAthlete()
  const deleteAthlete = useDeleteAthlete()

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<AthleteInput>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<AthleteInput & { is_hidden?: boolean }>({} as AthleteInput)
  const [statsOpenId, setStatsOpenId] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setFeedback(null)
    try {
      await createAthlete.mutateAsync(form)
      setFeedback({ kind: 'success', message: `Спортсмен «${form.full_name}» добавлен.` })
      setForm(EMPTY_FORM)
      setShowCreate(false)
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleUpdate(id: number) {
    setFeedback(null)
    try {
      await updateAthlete.mutateAsync({ id, payload: editForm })
      setFeedback({ kind: 'success', message: 'Изменения сохранены.' })
      setEditingId(null)
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleToggleHidden(id: number, name: string, hide: boolean) {
    setFeedback(null)
    try {
      await updateAthlete.mutateAsync({ id, payload: { is_hidden: hide } })
      setFeedback({ kind: 'success', message: `«${name}» ${hide ? 'скрыт с сайта' : 'снова виден на сайте'}.` })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Удалить спортсмена «${name}»? Это действие нельзя отменить.`)) return
    setFeedback(null)
    try {
      await deleteAthlete.mutateAsync(id)
      setFeedback({ kind: 'success', message: `«${name}» удалён.` })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-eyebrow text-rust">Единая база федерации</p>
          <h1 className="mt-2 font-display text-2xl text-bone">Спортсмены</h1>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim"
        >
          {showCreate ? 'Отмена' : '+ Добавить спортсмена'}
        </button>
      </div>

      {feedback && (
        <div className="mt-4">
          <FeedbackBanner kind={feedback.kind} message={feedback.message} />
        </div>
      )}

      {showCreate && (
        <form onSubmit={handleCreate} className="plate mt-4 flex flex-col gap-3 rounded-[var(--radius-rivet)] p-4">
          <input
            required
            placeholder="ФИО"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <div className="flex flex-wrap gap-3">
            <select
              value={form.gender}
              onChange={(e) => setForm({ ...form, gender: e.target.value as Gender })}
              className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            >
              <option value="male">Мужчины</option>
              <option value="female">Женщины</option>
            </select>
            <input
              type="date"
              value={form.birth_date ?? ''}
              onChange={(e) => setForm({ ...form, birth_date: e.target.value || undefined })}
              className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            />
            <input
              placeholder="Разряд"
              value={form.rank ?? ''}
              onChange={(e) => setForm({ ...form, rank: e.target.value || undefined })}
              className="w-32 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <select
              value={form.club_id ?? ''}
              onChange={(e) => setForm({ ...form, club_id: e.target.value ? Number(e.target.value) : undefined })}
              className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            >
              <option value="">Клуб — не указан</option>
              {clubs.data?.items.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              value={form.coach_id ?? ''}
              onChange={(e) => setForm({ ...form, coach_id: e.target.value ? Number(e.target.value) : undefined })}
              className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            >
              <option value="">Тренер — не указан</option>
              {coaches.data?.items.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.full_name}
                </option>
              ))}
            </select>
            <select
              value={form.city_id ?? ''}
              onChange={(e) => setForm({ ...form, city_id: e.target.value ? Number(e.target.value) : undefined })}
              className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            >
              <option value="">Город — не указан</option>
              {cities.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={createAthlete.isPending}
            className="self-start rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
          >
            {createAthlete.isPending ? 'Сохранение…' : 'Создать'}
          </button>
        </form>
      )}

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск по имени…"
        className="mt-6 w-full max-w-sm rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone placeholder:text-steel-dim focus:border-brass focus:outline-none"
      />

      <div className="mt-4">
        {athletes.isLoading && <LoadingState label="Загрузка спортсменов" />}
        {athletes.isError && <ErrorState message={(athletes.error as Error).message} onRetry={() => athletes.refetch()} />}
        {athletes.data && (
          <ul className="flex flex-col gap-3">
            {athletes.data.map((a) => (
              <li key={a.id} className="plate rounded-[var(--radius-rivet)] p-4">
                {editingId === a.id ? (
                  <div className="flex flex-col gap-3">
                    <input
                      defaultValue={a.full_name}
                      onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                      className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                    />
                    <div className="flex flex-wrap gap-3">
                      <input
                        placeholder="Разряд"
                        defaultValue={a.rank ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, rank: e.target.value || undefined })}
                        className="w-32 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                      />
                      <select
                        defaultValue=""
                        onChange={(e) => setEditForm({ ...editForm, club_id: e.target.value ? Number(e.target.value) : undefined })}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                      >
                        <option value="">Клуб: оставить «{a.club_name ?? 'не указан'}»</option>
                        {clubs.data?.items.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                      <select
                        defaultValue=""
                        onChange={(e) => setEditForm({ ...editForm, coach_id: e.target.value ? Number(e.target.value) : undefined })}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                      >
                        <option value="">Тренер: оставить «{a.coach_name ?? 'не указан'}»</option>
                        {coaches.data?.items.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.full_name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleUpdate(a.id)}
                        disabled={updateAthlete.isPending}
                        className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
                      >
                        Сохранить
                      </button>
                      <button
                        onClick={() => {
                          setEditingId(null)
                          setEditForm({} as AthleteInput)
                        }}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim px-4 py-2 text-sm text-steel hover:text-bone"
                      >
                        Отмена
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="flex items-center gap-2 font-display text-base text-bone">
                          {a.full_name}
                          {a.is_hidden && (
                            <span className="text-eyebrow rounded-[var(--radius-rivet)] bg-danger/15 px-2 py-0.5 text-danger">
                              скрыт
                            </span>
                          )}
                        </p>
                        <p className="font-mono text-xs text-steel">
                          {a.club_name ?? 'клуб не указан'} · {a.coach_name ?? 'без тренера'} · {a.rank ?? 'без разряда'}
                        </p>
                      </div>
                      <div className="flex flex-shrink-0 flex-wrap justify-end gap-2">
                        <button
                          onClick={() => setStatsOpenId(statsOpenId === a.id ? null : a.id)}
                          className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                        >
                          Статистика
                        </button>
                        <button
                          onClick={() => {
                            setEditingId(a.id)
                            setEditForm({} as AthleteInput)
                          }}
                          className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                        >
                          Изменить
                        </button>
                        <button
                          onClick={() => handleToggleHidden(a.id, a.full_name, !a.is_hidden)}
                          className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                        >
                          {a.is_hidden ? 'Показать' : 'Скрыть'}
                        </button>
                        {canDelete && (
                          <button
                            onClick={() => handleDelete(a.id, a.full_name)}
                            className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-danger hover:text-danger"
                          >
                            Удалить
                          </button>
                        )}
                      </div>
                    </div>
                    {statsOpenId === a.id && <StatisticsPanel athleteId={a.id} />}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function StatisticsPanel({ athleteId }: { athleteId: number }) {
  const stats = useAdminAthleteStatistics(athleteId)
  const updateStats = useUpdateAthleteStatistics()
  const recalc = useRecalculateAthleteStatistics()
  const [form, setForm] = useState<AthleteStatisticsUpdateInput>({})
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  async function handleSave() {
    setFeedback(null)
    try {
      await updateStats.mutateAsync({ id: athleteId, payload: form })
      setFeedback({ kind: 'success', message: 'Статистика обновлена вручную (is_manual_override = true).' })
      setForm({})
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleRecalc() {
    setFeedback(null)
    try {
      await recalc.mutateAsync(athleteId)
      setFeedback({ kind: 'success', message: 'Защита от пересчёта снята — статистику обновит следующая публикация турнира.' })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  if (stats.isLoading) return <div className="mt-3">{<LoadingState label="Загрузка статистики" />}</div>
  if (stats.isError) return <div className="mt-3">{<ErrorState message={(stats.error as Error).message} onRetry={() => stats.refetch()} />}</div>
  if (!stats.data) return null

  const s = stats.data

  return (
    <div className="mt-4 border-t border-steel-dim/30 pt-4">
      {s.is_manual_override && (
        <p className="text-eyebrow mb-3 text-brass">
          Правлено вручную{s.overridden_at ? ` · ${new Date(s.overridden_at).toLocaleString('ru-RU')}` : ''} — защищено от автопересчёта
        </p>
      )}
      <div className="grid grid-cols-2 gap-3 font-mono text-xs text-steel sm:grid-cols-4">
        <span>Турниров: {s.total_competitions}</span>
        <span>Побед: {s.total_wins}</span>
        <span>Поражений: {s.total_losses}</span>
        <span>Win-rate: {(s.win_rate * 100).toFixed(0)}%</span>
        <span>Золото: {s.gold_count}</span>
        <span>Серебро: {s.silver_count}</span>
        <span>Бронза: {s.bronze_count}</span>
      </div>

      <p className="text-eyebrow mt-4 text-steel">Ручная правка (например, сетевой сбой на площадке задвоил матч)</p>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(
          [
            ['total_wins', 'Победы'],
            ['total_losses', 'Поражения'],
            ['gold_count', 'Золото'],
            ['silver_count', 'Серебро'],
            ['bronze_count', 'Бронза'],
            ['total_competitions', 'Турниров'],
          ] as const
        ).map(([field, label]) => (
          <input
            key={field}
            type="number"
            placeholder={label}
            onChange={(e) => setForm({ ...form, [field]: e.target.value ? Number(e.target.value) : undefined })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-2 py-1.5 text-xs text-bone focus:border-brass focus:outline-none"
          />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={handleSave}
          disabled={updateStats.isPending || Object.keys(form).length === 0}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-1.5 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
        >
          Сохранить правку
        </button>
        {s.is_manual_override && (
          <button
            onClick={handleRecalc}
            disabled={recalc.isPending}
            className="rounded-[var(--radius-rivet)] border border-steel-dim px-4 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
          >
            Снять защиту (пересчитать заново)
          </button>
        )}
      </div>
      {feedback && (
        <div className="mt-3">
          <FeedbackBanner kind={feedback.kind} message={feedback.message} />
        </div>
      )}
    </div>
  )
}
