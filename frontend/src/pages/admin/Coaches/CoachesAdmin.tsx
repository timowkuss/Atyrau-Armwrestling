import { useState } from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import { useAdminClubsList } from '@/features/admin/useClubsAdmin'
import { useAdminCoachesList, useCreateCoach, useDeleteCoach, useUpdateCoach } from '@/features/admin/useCoachesAdmin'
import { useCities } from '@/features/useCities'
import { LoadingState, ErrorState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import { COACH_QUALIFICATIONS, type CoachInput } from '@/types/api'

const EMPTY_FORM: CoachInput = {
  first_name: '',
  last_name: '',
  birth_date: '',
  iin: '',
  qualification: COACH_QUALIFICATIONS[0],
  club_id: undefined,
  city_id: undefined,
  bio: '',
  photo_path: '',
}

const inputClass =
  'rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none'

function isValidIin(value: string) {
  return /^\d{12}$/.test(value)
}

export function CoachesAdmin() {
  const { user } = useAuth()
  const canDelete = user?.role_code === 'super_admin'
  const coaches = useAdminCoachesList()
  const clubs = useAdminClubsList()
  const cities = useCities()
  const createCoach = useCreateCoach()
  const updateCoach = useUpdateCoach()
  const deleteCoach = useDeleteCoach()

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<CoachInput>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<CoachInput>>({})
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setFeedback(null)
    if (!form.first_name.trim() || !form.last_name.trim()) {
      setFeedback({ kind: 'error', message: 'Укажите имя и фамилию тренера.' })
      return
    }
    if (!form.birth_date) {
      setFeedback({ kind: 'error', message: 'Укажите дату рождения (возраст).' })
      return
    }
    if (!isValidIin(form.iin)) {
      setFeedback({ kind: 'error', message: 'ИИН должен состоять ровно из 12 цифр.' })
      return
    }
    try {
      await createCoach.mutateAsync({ ...form, club_id: form.club_id || undefined, city_id: form.city_id || undefined })
      setFeedback({ kind: 'success', message: `Тренер «${form.last_name} ${form.first_name}» добавлен.` })
      setForm(EMPTY_FORM)
      setShowCreate(false)
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleUpdate(id: number) {
    setFeedback(null)
    if (editForm.iin !== undefined && editForm.iin !== '' && !isValidIin(editForm.iin)) {
      setFeedback({ kind: 'error', message: 'ИИН должен состоять ровно из 12 цифр.' })
      return
    }
    try {
      await updateCoach.mutateAsync({ id, payload: editForm })
      setFeedback({ kind: 'success', message: 'Изменения сохранены.' })
      setEditingId(null)
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Удалить тренера «${name}»?`)) return
    setFeedback(null)
    try {
      await deleteCoach.mutateAsync(id)
      setFeedback({ kind: 'success', message: `Тренер «${name}» удалён.` })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-eyebrow text-rust">Справочник федерации</p>
          <h1 className="mt-2 font-display text-2xl text-bone">Тренеры</h1>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim"
        >
          {showCreate ? 'Отмена' : '+ Добавить тренера'}
        </button>
      </div>

      {feedback && (
        <div className="mt-4">
          <FeedbackBanner kind={feedback.kind} message={feedback.message} />
        </div>
      )}

      {showCreate && (
        <form onSubmit={handleCreate} className="plate mt-4 flex flex-col gap-3 rounded-[var(--radius-rivet)] p-4">
          <div className="flex flex-wrap gap-3">
            <input
              required
              placeholder="Имя"
              value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
              className={inputClass}
            />
            <input
              required
              placeholder="Фамилия"
              value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
              className={inputClass}
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <input
              required
              type="date"
              title="Дата рождения (возраст)"
              value={form.birth_date}
              onChange={(e) => setForm({ ...form, birth_date: e.target.value })}
              className={inputClass}
            />
            <input
              required
              placeholder="ИИН (12 цифр)"
              inputMode="numeric"
              maxLength={12}
              pattern="\d{12}"
              value={form.iin}
              onChange={(e) => setForm({ ...form, iin: e.target.value.replace(/\D/g, '').slice(0, 12) })}
              className={`w-40 ${inputClass}`}
            />
            <select
              value={form.qualification ?? COACH_QUALIFICATIONS[0]}
              onChange={(e) => setForm({ ...form, qualification: e.target.value })}
              className={inputClass}
            >
              {COACH_QUALIFICATIONS.map((q) => (
                <option key={q} value={q}>
                  {q}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-wrap gap-3">
            <select
              value={form.club_id ?? ''}
              onChange={(e) => setForm({ ...form, club_id: e.target.value ? Number(e.target.value) : undefined })}
              className={inputClass}
            >
              <option value="">Клуб — не указан</option>
              {clubs.data?.items.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              value={form.city_id ?? ''}
              onChange={(e) => setForm({ ...form, city_id: e.target.value ? Number(e.target.value) : undefined })}
              className={inputClass}
            >
              <option value="">Город/Район — не указан</option>
              {cities.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.region_name})
                </option>
              ))}
            </select>
          </div>
          <textarea
            placeholder="Биография"
            value={form.bio ?? ''}
            onChange={(e) => setForm({ ...form, bio: e.target.value })}
            rows={2}
            className={inputClass}
          />
          <button
            type="submit"
            disabled={createCoach.isPending}
            className="self-start rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
          >
            {createCoach.isPending ? 'Сохранение…' : 'Создать'}
          </button>
        </form>
      )}

      <div className="mt-6">
        {coaches.isLoading && <LoadingState label="Загрузка тренеров" />}
        {coaches.isError && <ErrorState message={(coaches.error as Error).message} onRetry={() => coaches.refetch()} />}
        {coaches.data && (
          <ul className="flex flex-col gap-3">
            {coaches.data.items.map((coach) => (
              <li key={coach.id} className="plate rounded-[var(--radius-rivet)] p-4">
                {editingId === coach.id ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap gap-3">
                      <input
                        placeholder="ИИН: оставить прежний"
                        inputMode="numeric"
                        maxLength={12}
                        defaultValue={coach.iin ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, iin: e.target.value.replace(/\D/g, '').slice(0, 12) })}
                        className={`w-48 ${inputClass}`}
                      />
                      <select
                        defaultValue=""
                        onChange={(e) => setEditForm({ ...editForm, qualification: e.target.value || undefined })}
                        className={inputClass}
                      >
                        <option value="">Звание: оставить «{coach.qualification ?? 'не указано'}»</option>
                        {COACH_QUALIFICATIONS.map((q) => (
                          <option key={q} value={q}>
                            {q}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      <select
                        defaultValue=""
                        onChange={(e) => setEditForm({ ...editForm, club_id: e.target.value ? Number(e.target.value) : undefined })}
                        className={inputClass}
                      >
                        <option value="">Клуб: оставить «{coach.club_name ?? 'не указан'}»</option>
                        {clubs.data?.items.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                      <select
                        defaultValue=""
                        onChange={(e) => setEditForm({ ...editForm, city_id: e.target.value ? Number(e.target.value) : undefined })}
                        className={inputClass}
                      >
                        <option value="">Город: оставить «{coach.city_name ?? 'не указан'}»</option>
                        {cities.data?.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name} ({c.region_name})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleUpdate(coach.id)}
                        disabled={updateCoach.isPending}
                        className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
                      >
                        Сохранить
                      </button>
                      <button
                        onClick={() => {
                          setEditingId(null)
                          setEditForm({})
                        }}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim px-4 py-2 text-sm text-steel hover:text-bone"
                      >
                        Отмена
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="font-display text-base text-bone">{coach.full_name}</p>
                      <p className="font-mono text-xs text-steel">
                        {coach.club_name ?? 'клуб не указан'} · {coach.city_name ?? 'город не указан'} ·{' '}
                        {coach.qualification ?? 'без звания'} · {coach.athletes_count} спортсменов
                      </p>
                      <p className="font-mono text-xs text-steel-dim">ИИН: {coach.iin ?? '—'}</p>
                    </div>
                    <div className="flex flex-shrink-0 gap-2">
                      <button
                        onClick={() => {
                          setEditingId(coach.id)
                          setEditForm({})
                        }}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                      >
                        Изменить
                      </button>
                      {canDelete && (
                        <button
                          onClick={() => handleDelete(coach.id, coach.full_name)}
                          className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-danger hover:text-danger"
                        >
                          Удалить
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
