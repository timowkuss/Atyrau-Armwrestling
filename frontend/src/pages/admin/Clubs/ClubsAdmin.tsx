import { useState } from 'react'
import { useAuth } from '@/features/auth/useAuth'
import {
  useAddClubMembers,
  useAdminClubDetail,
  useAdminClubsList,
  useCreateClub,
  useDeleteClub,
  useRemoveClubMembers,
  useUpdateClub,
} from '@/features/admin/useClubsAdmin'
import { useAdminAthletes } from '@/features/admin/useAthletesAdmin'
import { useAdminCoachesList } from '@/features/admin/useCoachesAdmin'
import { LoadingState, ErrorState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import { CityCombobox } from '@/components/admin/CityCombobox'
import { PhotoUploadField } from '@/components/admin/PhotoUploadField'
import { cloudinaryLogo } from '@/lib/cloudinaryImage'
import { blockNonDigits, blockPhonePrefix, formatPhone, formatPhoneChange } from '@/lib/phoneMask'
import type { ClubInput } from '@/types/api'

const EMPTY_FORM: ClubInput = { name: '', description: '', address: '', phone: '8(', city_id: undefined, founded_date: undefined, logo_path: '' }

function LogoThumb({ url, name }: { url: string | null; name: string }) {
  return (
    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl border border-steel-dim/20 bg-ink font-display text-sm text-steel">
      {url ? (
        <img src={cloudinaryLogo(url, 48) ?? url} alt="" className="h-full w-full object-contain p-0.5" />
      ) : (
        name.charAt(0)
      )}
    </div>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  if (!y || !m || !d) return iso
  return `${d}.${m}.${y}`
}

export function ClubsAdmin() {
  const { user } = useAuth()
  const canDelete = user?.role_code === 'super_admin'
  const clubs = useAdminClubsList()
  const createClub = useCreateClub()
  const updateClub = useUpdateClub()
  const deleteClub = useDeleteClub()
  const addMembers = useAddClubMembers()
  const removeMembers = useRemoveClubMembers()

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<ClubInput>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<ClubInput>>({})
  const [manageId, setManageId] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  const detail = useAdminClubDetail(manageId)
  const athletes = useAdminAthletes()
  const coaches = useAdminCoachesList()

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setFeedback(null)
    if (nameTaken) {
      setFeedback({ kind: 'error', message: 'Клуб с таким названием уже существует.' })
      return
    }
    if (!form.city_id) {
      setFeedback({ kind: 'error', message: 'Укажите город/область клуба.' })
      return
    }
    try {
      await createClub.mutateAsync({
        ...form,
        city_id: form.city_id || undefined,
        founded_date: form.founded_date || undefined,
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
    if (!confirm(`Удалить клуб «${name}»? Спортсмены и тренеры останутся без клуба.`)) return
    setFeedback(null)
    try {
      await deleteClub.mutateAsync(id)
      setFeedback({ kind: 'success', message: `Клуб «${name}» удалён.` })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  const memberAthleteIds = new Set((detail.data?.athletes ?? []).map((a) => a.id))
  const memberCoachIds = new Set((detail.data?.coaches ?? []).map((c) => c.id))

  const freeAthletes = (athletes.data ?? []).filter((a) => !memberAthleteIds.has(a.id))
  const freeCoaches = (coaches.data?.items ?? []).filter((c) => !memberCoachIds.has(c.id))

  const nameTaken = form.name.trim().length > 0 && (clubs.data ?? []).some(
    (c) => c.name.trim().toLowerCase() === form.name.trim().toLowerCase(),
  )

  const [newAthleteId, setNewAthleteId] = useState('')
  const [newCoachId, setNewCoachId] = useState('')

  async function addAthlete() {
    if (!manageId || !newAthleteId) return
    setFeedback(null)
    try {
      await addMembers.mutateAsync({ id: manageId, payload: { athlete_ids: [Number(newAthleteId)], coach_ids: [] } })
      setNewAthleteId('')
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function addCoach() {
    if (!manageId || !newCoachId) return
    setFeedback(null)
    try {
      await addMembers.mutateAsync({ id: manageId, payload: { athlete_ids: [], coach_ids: [Number(newCoachId)] } })
      setNewCoachId('')
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function removeAthlete(aid: number) {
    if (!manageId) return
    setFeedback(null)
    try {
      await removeMembers.mutateAsync({ id: manageId, payload: { athlete_ids: [aid], coach_ids: [] } })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function removeCoach(cid: number) {
    if (!manageId) return
    setFeedback(null)
    try {
      await removeMembers.mutateAsync({ id: manageId, payload: { athlete_ids: [], coach_ids: [cid] } })
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
          <div>
            <input
              required
              placeholder="Название клуба *"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className={`w-full rounded-[var(--radius-rivet)] border bg-ink px-3 py-2 text-sm text-bone focus:outline-none ${
                nameTaken
                  ? 'border-danger focus:border-danger'
                  : 'border-steel-dim focus:border-brass'
              }`}
            />
            {nameTaken && (
              <p className="mt-1 text-xs font-medium text-danger">Такой клуб уже существует</p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <CityCombobox
              required
              placeholder="Город / область *"
              className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
              onChange={(cityId) => setForm({ ...form, city_id: cityId })}
            />
            <input
              type="date"
              placeholder="Дата основания"
              value={form.founded_date ?? ''}
              onChange={(e) => setForm({ ...form, founded_date: e.target.value || undefined })}
              className="w-full sm:w-44 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            />
          </div>
          <textarea
            placeholder="Адрес зала"
            value={form.address ?? ''}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
            rows={2}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <input
            placeholder="Телефон 8(XXX)XXX-XX-XX"
            value={form.phone ?? '8('}
            onChange={(e) => setForm({ ...form, phone: formatPhoneChange(form.phone, e.target.value) })}
            onKeyDown={(e) => {
              blockNonDigits(e)
              blockPhonePrefix(e)
            }}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <div>
            <p className="mb-1 font-mono text-xs text-steel-dim">Логотип</p>
            <PhotoUploadField
              value={form.logo_path}
              onChange={(url) => setForm({ ...form, logo_path: url })}
              shape="square"
              size={72}
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
            {clubs.data.map((club) => (
              <li key={club.id} className="plate rounded-[var(--radius-rivet)] p-4">
                {editingId === club.id ? (
                  <div className="flex flex-col gap-3">
                    <input
                      defaultValue={club.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                    />
                    <div className="flex flex-wrap gap-3">
                      <CityCombobox
                        initialText={club.city_name ?? ''}
                        placeholder="Город"
                        className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                        onChange={(cityId) => setEditForm({ ...editForm, city_id: cityId })}
                      />
                      <input
                        type="date"
                        placeholder="Дата основания"
                        defaultValue={club.founded_date ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, founded_date: e.target.value || undefined })}
                        className="w-full sm:w-44 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                      />
                    </div>
                    <div>
                      <p className="mb-1 font-mono text-xs text-steel-dim">Логотип</p>
                      <PhotoUploadField
                        value={editForm.logo_path}
                        fallbackPreview={club.logo_path}
                        onChange={(url) => setEditForm({ ...editForm, logo_path: url })}
                        shape="square"
                        size={72}
                      />
                    </div>
                    <input
                      placeholder="Адрес зала"
                      defaultValue={club.address ?? ''}
                      onChange={(e) => setEditForm({ ...editForm, address: e.target.value })}
                      className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                    />
                    <input
                      placeholder="Телефон 8(XXX)XXX-XX-XX"
                      inputMode="tel"
                      value={formatPhone(editForm.phone ?? club.phone ?? '')}
                      onKeyDown={(e) => {
                        blockPhonePrefix(e)
                        blockNonDigits(e)
                      }}
                      onChange={(e) =>
                        setEditForm({ ...editForm, phone: formatPhoneChange(editForm.phone ?? club.phone ?? '', e.target.value) })
                      }
                      className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
                    />
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
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <div className="flex min-w-0 items-center gap-3">
                        <LogoThumb url={club.logo_path} name={club.name} />
                        <div className="min-w-0">
                          <p className="truncate font-display text-base text-bone">{club.name}</p>
                          <p className="font-mono text-xs text-steel">
                            {club.city_name ?? 'город не указан'} · {club.athletes_count} спортсменов · {club.coaches_count} тренеров · рейтинг {club.rating_points}
                          </p>
                          {club.phone && <p className="font-mono text-xs text-steel-dim">📞 {club.phone}</p>}
                          {club.address && <p className="truncate font-mono text-xs text-steel-dim">📍 {club.address}</p>}
                          {formatDate(club.founded_date) && (
                            <p className="font-mono text-xs text-steel-dim">📅 осн. {formatDate(club.founded_date)}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => {
                            setManageId(manageId === club.id ? null : club.id)
                            setNewAthleteId('')
                            setNewCoachId('')
                          }}
                          className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                        >
                          {manageId === club.id ? 'Скрыть состав' : 'Состав'}
                        </button>
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

                    {manageId === club.id && (
                      <div className="mt-4 border-t border-steel-dim/15 pt-4">
                        {detail.isLoading && <p className="font-mono text-xs text-steel-dim">Загрузка состава…</p>}
                        {detail.isError && (
                          <ErrorState message={(detail.error as Error).message} onRetry={() => detail.refetch()} />
                        )}
                        {detail.data && (
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <p className="text-eyebrow mb-2 text-brass">Спортсмены ({detail.data.athletes.length})</p>
                              <ul className="flex flex-col gap-1.5">
                                {detail.data.athletes.map((a) => (
                                  <li key={a.id} className="flex items-center justify-between gap-2 rounded-xl border border-steel-dim/15 bg-ink/50 px-3 py-1.5">
                                    <span className="truncate text-sm text-bone">{a.full_name}</span>
                                    <button
                                      onClick={() => removeAthlete(a.id)}
                                      className="flex-shrink-0 font-mono text-xs text-steel hover:text-danger"
                                    >
                                      убрать
                                    </button>
                                  </li>
                                ))}
                                {detail.data.athletes.length === 0 && (
                                  <li className="font-mono text-xs text-steel-dim">Спортсменов пока нет</li>
                                )}
                              </ul>
                              <div className="mt-2 flex gap-2">
                                <select
                                  value={newAthleteId}
                                  onChange={(e) => setNewAthleteId(e.target.value)}
                                  className="min-w-0 flex-1 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-1.5 text-sm text-bone focus:border-brass focus:outline-none"
                                >
                                  <option value="">— добавить спортсмена —</option>
                                  {freeAthletes.map((a) => (
                                    <option key={a.id} value={a.id}>{a.full_name}</option>
                                  ))}
                                </select>
                                <button
                                  onClick={addAthlete}
                                  disabled={!newAthleteId || addMembers.isPending}
                                  className="rounded-[var(--radius-rivet)] bg-rust px-3 py-1.5 text-sm text-bone hover:bg-rust-dim disabled:opacity-50"
                                >
                                  +
                                </button>
                              </div>
                              {freeAthletes.length === 0 && (
                                <p className="mt-1 font-mono text-xs text-steel-dim">Все спортсмены уже в клубах</p>
                              )}
                            </div>

                            <div>
                              <p className="text-eyebrow mb-2 text-brass">Тренеры ({detail.data.coaches.length})</p>
                              <ul className="flex flex-col gap-1.5">
                                {detail.data.coaches.map((c) => (
                                  <li key={c.id} className="flex items-center justify-between gap-2 rounded-xl border border-steel-dim/15 bg-ink/50 px-3 py-1.5">
                                    <span className="truncate text-sm text-bone">{c.full_name}</span>
                                    <button
                                      onClick={() => removeCoach(c.id)}
                                      className="flex-shrink-0 font-mono text-xs text-steel hover:text-danger"
                                    >
                                      убрать
                                    </button>
                                  </li>
                                ))}
                                {detail.data.coaches.length === 0 && (
                                  <li className="font-mono text-xs text-steel-dim">Тренеров пока нет</li>
                                )}
                              </ul>
                              <div className="mt-2 flex gap-2">
                                <select
                                  value={newCoachId}
                                  onChange={(e) => setNewCoachId(e.target.value)}
                                  className="min-w-0 flex-1 rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-1.5 text-sm text-bone focus:border-brass focus:outline-none"
                                >
                                  <option value="">— добавить тренера —</option>
                                  {freeCoaches.map((c) => (
                                    <option key={c.id} value={c.id}>{c.full_name}</option>
                                  ))}
                                </select>
                                <button
                                  onClick={addCoach}
                                  disabled={!newCoachId || addMembers.isPending}
                                  className="rounded-[var(--radius-rivet)] bg-rust px-3 py-1.5 text-sm text-bone hover:bg-rust-dim disabled:opacity-50"
                                >
                                  +
                                </button>
                              </div>
                              {freeCoaches.length === 0 && (
                                <p className="mt-1 font-mono text-xs text-steel-dim">Все тренеры уже в клубах</p>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
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
