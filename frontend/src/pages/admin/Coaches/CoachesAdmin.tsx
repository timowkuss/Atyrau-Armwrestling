import { useState } from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import { useAdminClubsList } from '@/features/admin/useClubsAdmin'
import { useAdminCoachesList, useCreateCoach, useDeleteCoach, useUpdateCoach } from '@/features/admin/useCoachesAdmin'
import { LoadingState, ErrorState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import type { CoachInput } from '@/types/api'

const EMPTY_FORM: CoachInput = { full_name: '', bio: '', club_id: undefined, photo_path: '' }

export function CoachesAdmin() {
  const { user } = useAuth()
  const canDelete = user?.role_code === 'super_admin'
  const coaches = useAdminCoachesList()
  const clubs = useAdminClubsList()
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
    try {
      await createCoach.mutateAsync({ ...form, club_id: form.club_id || undefined })
      setFeedback({ kind: 'success', message: `Тренер «${form.full_name}» добавлен.` })
      setForm(EMPTY_FORM)
      setShowCreate(false)
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleUpdate(id: number) {
    setFeedback(null)
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
      <div className="flex items-center justify-between">
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
          <input
            required
            placeholder="ФИО тренера"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <textarea
            placeholder="Биография"
            value={form.bio ?? ''}
            onChange={(e) => setForm({ ...form, bio: e.target.value })}
            rows={2}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
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
                    <input
                      defaultValue={coach.full_name}
                      onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                      className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                    />
                    <select
                      defaultValue=""
                      onChange={(e) => setEditForm({ ...editForm, club_id: e.target.value ? Number(e.target.value) : undefined })}
                      className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                    >
                      <option value="">Клуб: оставить «{coach.club_name ?? 'не указан'}»</option>
                      {clubs.data?.items.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
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
                        {coach.club_name ?? 'клуб не указан'} · {coach.athletes_count} спортсменов
                      </p>
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
