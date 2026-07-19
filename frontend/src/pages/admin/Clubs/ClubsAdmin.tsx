import { useState } from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import { useCities } from '@/features/useCities'
import { useAdminClubsList, useCreateClub, useDeleteClub, useUpdateClub } from '@/features/admin/useClubsAdmin'
import { LoadingState, ErrorState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import type { ClubInput } from '@/types/api'

const EMPTY_FORM: ClubInput = { name: '', description: '', city_id: undefined, founded_year: undefined, logo_path: '' }

export function ClubsAdmin() {
  const { user } = useAuth()
  const canDelete = user?.role_code === 'super_admin'
  const clubs = useAdminClubsList()
  const cities = useCities()
  const createClub = useCreateClub()
  const updateClub = useUpdateClub()
  const deleteClub = useDeleteClub()

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<ClubInput>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<ClubInput>>({})
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setFeedback(null)
    try {
      await createClub.mutateAsync({
        ...form,
        city_id: form.city_id || undefined,
        founded_year: form.founded_year || undefined,
      })
      setFeedback({ kind: 'success', message: `Клуб «${form.name}» создан.` })
      setForm(EMPTY_FORM)
      setShowCreate(false)
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleUpdate(id: number) {
    setFeedback(null)
    try {
      await updateClub.mutateAsync({ id, payload: editForm })
      setFeedback({ kind: 'success', message: 'Изменения сохранены.' })
      setEditingId(null)
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Удалить клуб «${name}»? Это действие нельзя отменить.`)) return
    setFeedback(null)
    try {
      await deleteClub.mutateAsync(id)
      setFeedback({ kind: 'success', message: `Клуб «${name}» удалён.` })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-eyebrow text-rust">Справочник федерации</p>
          <h1 className="mt-2 font-display text-2xl text-bone">Клубы</h1>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim"
        >
          {showCreate ? 'Отмена' : '+ Добавить клуб'}
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
            placeholder="Название клуба"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <textarea
            placeholder="Описание"
            value={form.description ?? ''}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={2}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <div className="flex flex-wrap gap-3">
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
            <input
              type="number"
              placeholder="Год основания"
              value={form.founded_year ?? ''}
              onChange={(e) => setForm({ ...form, founded_year: e.target.value ? Number(e.target.value) : undefined })}
              className="w-40 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={createClub.isPending}
            className="self-start rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
          >
            {createClub.isPending ? 'Сохранение…' : 'Создать'}
          </button>
        </form>
      )}

      <div className="mt-6">
        {clubs.isLoading && <LoadingState label="Загрузка клубов" />}
        {clubs.isError && <ErrorState message={(clubs.error as Error).message} onRetry={() => clubs.refetch()} />}
        {clubs.data && (
          <ul className="flex flex-col gap-3">
            {clubs.data.items.map((club) => (
              <li key={club.id} className="plate rounded-[var(--radius-rivet)] p-4">
                {editingId === club.id ? (
                  <div className="flex flex-col gap-3">
                    <input
                      defaultValue={club.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                    />
                    <div className="flex flex-wrap gap-3">
                      <select
                        defaultValue=""
                        onChange={(e) => setEditForm({ ...editForm, city_id: e.target.value ? Number(e.target.value) : undefined })}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                      >
                        <option value="">Город: оставить «{club.city_name ?? 'не указан'}»</option>
                        {cities.data?.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                      <input
                        type="number"
                        placeholder="Год основания"
                        onChange={(e) => setEditForm({ ...editForm, founded_year: e.target.value ? Number(e.target.value) : undefined })}
                        className="w-40 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleUpdate(club.id)}
                        disabled={updateClub.isPending}
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
                      <p className="font-display text-base text-bone">{club.name}</p>
                      <p className="font-mono text-xs text-steel">
                        {club.city_name ?? 'город не указан'} · {club.athletes_count} спортсменов · рейтинг {club.rating_points}
                      </p>
                    </div>
                    <div className="flex flex-shrink-0 gap-2">
                      <button
                        onClick={() => {
                          setEditingId(club.id)
                          setEditForm({})
                        }}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                      >
                        Изменить
                      </button>
                      {canDelete && (
                        <button
                          onClick={() => handleDelete(club.id, club.name)}
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
