import { useState } from 'react'
import { useAuth } from '@/features/auth/useAuth'
import { useAdminClubsList } from '@/features/admin/useClubsAdmin'
import { useAdminCoachesList, useCreateCoach, useDeleteCoach, useUpdateCoach } from '@/features/admin/useCoachesAdmin'
import { LoadingState, ErrorState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import { PhotoUploadField } from '@/components/admin/PhotoUploadField'
import { cloudinaryThumb } from '@/lib/cloudinaryImage'
import { CityCombobox } from '@/components/admin/CityCombobox'
import { blockNonDigits, blockPhonePrefix, formatPhone, formatPhoneChange } from '@/lib/phoneMask'
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
  phone: '8(',
}

const inputClass =
  'w-full sm:w-auto rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none'

function isValidIin(value: string) {
  return /^\d{12}$/.test(value)
}

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

  const createIinConflict = form.iin
    ? (coaches.data?.items.find((c) => c.iin === form.iin) ?? null)
    : null
  const editingCoach = editingId !== null ? (coaches.data?.items.find((c) => c.id === editingId) ?? null) : null
  const editIinValue = editForm.iin ?? editingCoach?.iin ?? null
  const editIinConflict = editIinValue
    ? (coaches.data?.items.find((c) => c.iin === editIinValue && c.id !== editingId) ?? null)
    : null

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
    if (createIinConflict) {
      setFeedback({ kind: 'error', message: `Тренер с таким ИИН уже существует: ${createIinConflict.full_name}` })
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
    if (editIinConflict) {
      setFeedback({ kind: 'error', message: `Тренер с таким ИИН уже существует: ${editIinConflict.full_name}` })
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

  async function handleToggleHidden(id: number, name: string, hide: boolean) {
    setFeedback(null)
    try {
      await updateCoach.mutateAsync({ id, payload: { is_hidden: hide } })
      setFeedback({ kind: 'success', message: `«${name}» ${hide ? 'скрыт с сайта' : 'снова виден на сайте'}.` })
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
            <div className="flex flex-col gap-1">
              <input
                required
                placeholder="ИИН (12 цифр)"
                inputMode="numeric"
                maxLength={12}
                pattern="\d{12}"
                value={form.iin}
                onKeyDown={blockNonDigits}
                onChange={(e) => setForm({ ...form, iin: e.target.value.replace(/\D/g, '').slice(0, 12) })}
                className={`w-full sm:w-40 ${inputClass}`}
              />
              {createIinConflict && (
                <p className="text-xs text-red-400">
                  Тренер с таким ИИН уже существует: {createIinConflict.full_name}
                </p>
              )}
            </div>
            <input
              placeholder="Телефон 8(XXX)XXX-XX-XX"
              inputMode="tel"
              value={form.phone ?? '8('}
              onKeyDown={(e) => {
                blockPhonePrefix(e)
                blockNonDigits(e)
              }}
              onChange={(e) => setForm({ ...form, phone: formatPhoneChange(form.phone, e.target.value) })}
              className={inputClass}
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
              {clubs.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <CityCombobox
              placeholder="Город/Район"
              className={inputClass}
              onChange={(cityId) => setForm({ ...form, city_id: cityId })}
            />
          </div>
          <PhotoUploadField
            value={form.photo_path}
            onChange={(url) => setForm({ ...form, photo_path: url })}
            shape="square"
            size={96}
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
          <>
            <ul className="flex flex-col gap-3">
            {coaches.data.items
              .filter((coach) => !coach.is_hidden)
              .map((coach) => (
              <li key={coach.id} className="plate rounded-[var(--radius-rivet)] p-4">
                {editingId === coach.id ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap gap-3">
                      <input
                        placeholder="Имя"
                        defaultValue={coach.first_name ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                        className={inputClass}
                      />
                      <input
                        placeholder="Фамилия"
                        defaultValue={coach.last_name ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                        className={inputClass}
                      />
                    </div>
                    <div className="flex flex-wrap gap-3">
                      <div className="flex flex-col gap-1">
                        <input
                          placeholder="ИИН: оставить прежний"
                          inputMode="numeric"
                          maxLength={12}
                          value={editForm.iin ?? coach.iin ?? ''}
                          onKeyDown={blockNonDigits}
                          onChange={(e) => setEditForm({ ...editForm, iin: e.target.value.replace(/\D/g, '').slice(0, 12) })}
                          className={`w-full sm:w-48 ${inputClass}`}
                        />
                        {editIinConflict && (
                          <p className="text-xs text-red-400">
                            Тренер с таким ИИН уже существует: {editIinConflict.full_name}
                          </p>
                        )}
                      </div>
                      <input
                        placeholder="Телефон 8(XXX)XXX-XX-XX"
                        inputMode="tel"
                        value={formatPhone(editForm.phone ?? coach.phone ?? '')}
                        onKeyDown={(e) => {
                          blockPhonePrefix(e)
                          blockNonDigits(e)
                        }}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            phone: formatPhoneChange(editForm.phone ?? coach.phone ?? '', e.target.value),
                          })
                        }
                        className={inputClass}
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
                        onChange={(e) => {
                          const v = e.target.value
                          setEditForm({
                            ...editForm,
                            club_id: v === 'none' ? null : v ? Number(v) : undefined,
                          })
                        }}
                        className={inputClass}
                      >
                        <option value="">Клуб: оставить «{coach.club_name ?? 'не указан'}»</option>
                        <option value="none">Без клуба</option>
                        {clubs.data?.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                      <CityCombobox
                        initialText={coach.city_name ?? ''}
                        placeholder="Город/Район"
                        className={inputClass}
                        onChange={(cityId) => setEditForm({ ...editForm, city_id: cityId })}
                      />
                    </div>
                    <PhotoUploadField
                      value={editForm.photo_path}
                      fallbackPreview={coach.photo_path}
                      onChange={(url) => setEditForm({ ...editForm, photo_path: url })}
                      shape="square"
                      size={96}
                    />
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
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div className="flex min-w-0 items-center gap-3">
                      {coach.photo_path ? (
                        <img
                          src={cloudinaryThumb(coach.photo_path, 64) ?? undefined}
                          alt=""
                          className="h-16 w-16 flex-shrink-0 rounded-2xl object-cover border border-steel-dim"
                          onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                        />
                      ) : (
                        <div className="h-16 w-16 flex-shrink-0 rounded-2xl bg-ink border border-steel-dim" />
                      )}
                      <div className="min-w-0">
                        <p className="truncate font-display text-base text-bone">{coach.full_name}</p>
                        <p className="truncate font-mono text-xs text-steel">
                          {coach.club_name ?? 'клуб не указан'} · {coach.city_name ?? 'город не указан'} ·{' '}
                          {coach.qualification ?? 'без звания'} · {coach.athletes_count} спортсменов
                        </p>
                        <p className="truncate font-mono text-xs text-steel-dim">ИИН: {coach.iin ?? '—'}</p>
                        <p className="truncate font-mono text-xs text-steel-dim">Телефон: {coach.phone ?? '—'}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => {
                          setEditingId(coach.id)
                          setEditForm({})
                        }}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                      >
                        Изменить
                      </button>
                      <button
                        onClick={() => handleToggleHidden(coach.id, coach.full_name, true)}
                        className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                      >
                        Скрыть
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

            {coaches.data.items.filter((c) => c.is_hidden).length > 0 && (
              <div className="mt-6">
                <h2 className="text-eyebrow text-amber">
                  Скрытые — удалённые с сайта ({coaches.data.items.filter((c) => c.is_hidden).length})
                </h2>
                <div className="mt-3 flex gap-4 overflow-x-auto pb-2">
                  {coaches.data.items
                    .filter((c) => c.is_hidden)
                    .map((coach) => (
                      <div key={coach.id} className="plate w-56 flex-shrink-0 rounded-[var(--radius-rivet)] p-3">
                        <div className="flex items-start gap-3">
                          {coach.photo_path ? (
                            <img
                              src={cloudinaryThumb(coach.photo_path, 96) ?? undefined}
                              alt=""
                              className="h-14 w-14 flex-shrink-0 rounded-2xl object-cover border border-steel-dim"
                              onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                            />
                          ) : (
                            <div className="h-14 w-14 flex-shrink-0 rounded-2xl bg-ink border border-steel-dim" />
                          )}
                          <div className="min-w-0">
                            <p className="truncate font-display text-sm text-bone">{coach.full_name}</p>
                            <p className="mt-1 truncate font-mono text-xs text-steel">
                              {coach.club_name ?? 'без клуба'} · {coach.athletes_count} спортсменов
                            </p>
                          </div>
                        </div>
                        <div className="mt-3 flex gap-2">
                          <button
                            onClick={() => handleToggleHidden(coach.id, coach.full_name, false)}
                            className="flex-1 rounded-[var(--radius-rivet)] border border-steel-dim px-2 py-1.5 text-xs text-steel hover:border-brass hover:text-brass"
                          >
                            Показать
                          </button>
                          {canDelete && (
                            <button
                              onClick={() => handleDelete(coach.id, coach.full_name)}
                              className="flex-1 rounded-[var(--radius-rivet)] border border-steel-dim px-2 py-1.5 text-xs text-steel hover:border-danger hover:text-danger"
                            >
                              Удалить
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
