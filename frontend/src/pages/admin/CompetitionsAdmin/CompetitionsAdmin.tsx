import { useState } from 'react'
import {
  useAdminCompetitions,
  useAdminDocuments,
  useCreateDocument,
  useDeleteDocument,
  useUpdateCompetition,
} from '@/features/admin/useCompetitionsAdmin'
import { useCities } from '@/features/useCities'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import type { CompetitionAdminUpdateInput, GalleryDocumentInput } from '@/types/api'

export function CompetitionsAdmin() {
  const competitions = useAdminCompetitions()
  const [openId, setOpenId] = useState<number | null>(null)

  return (
    <div>
      <p className="text-eyebrow text-rust">Турниры — только информационная часть</p>
      <h1 className="mt-2 font-display text-2xl text-bone">Соревнования</h1>
      <p className="mt-2 max-w-2xl text-steel">
        Здесь редактируются описание, афиша, регламент и город турнира. Сетка, участники,
        матчи, результаты и очки — исключительно из десктоп-приложения на площадке; на сайте
        эти поля физически недоступны для правки.
      </p>

      <div className="mt-6">
        {competitions.isLoading && <LoadingState label="Загрузка турниров" />}
        {competitions.isError && (
          <ErrorState message={(competitions.error as Error).message} onRetry={() => competitions.refetch()} />
        )}
        {competitions.data && competitions.data.length === 0 && <EmptyState title="Турниров пока нет" />}
        {competitions.data && competitions.data.length > 0 && (
          <ul className="flex flex-col gap-3">
            {competitions.data.map((c) => (
              <li key={c.id} className="plate rounded-[var(--radius-rivet)] p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-display text-base text-bone">{c.name}</p>
                    <p className="font-mono text-xs text-steel">
                      {new Date(c.date).toLocaleDateString('ru-RU')} · {c.location_city_name ?? 'город не указан'} ·{' '}
                      <span className={c.status === 'published' ? 'text-success' : 'text-steel'}>{c.status}</span>
                    </p>
                  </div>
                  <button
                    onClick={() => setOpenId(openId === c.id ? null : c.id)}
                    className="flex-shrink-0 rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                  >
                    {openId === c.id ? 'Скрыть' : 'Редактировать'}
                  </button>
                </div>
                {openId === c.id && (
                  <CompetitionEditPanel
                    competitionId={c.id}
                    initial={{
                      description: c.description,
                      poster_path: c.poster_path,
                      regulations_doc_path: c.regulations_doc_path,
                    }}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function CompetitionEditPanel({
  competitionId,
  initial,
}: {
  competitionId: number
  initial: { description: string | null; poster_path: string | null; regulations_doc_path: string | null }
}) {
  const updateCompetition = useUpdateCompetition()
  const cities = useCities()
  const documents = useAdminDocuments(competitionId)
  const createDocument = useCreateDocument()
  const deleteDocument = useDeleteDocument()

  const [form, setForm] = useState<CompetitionAdminUpdateInput>({
    description: initial.description ?? '',
    poster_path: initial.poster_path ?? '',
    regulations_doc_path: initial.regulations_doc_path ?? '',
  })
  const [docForm, setDocForm] = useState<Omit<GalleryDocumentInput, 'competition_id'>>({ title: '', file_path: '', doc_type: 'regulations' })
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  async function handleSave() {
    setFeedback(null)
    try {
      await updateCompetition.mutateAsync({ id: competitionId, payload: form })
      setFeedback({ kind: 'success', message: 'Информация о турнире обновлена.' })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleAddDocument(e: React.FormEvent) {
    e.preventDefault()
    setFeedback(null)
    try {
      await createDocument.mutateAsync({ competitionId, payload: { competition_id: competitionId, ...docForm } })
      setFeedback({ kind: 'success', message: 'Документ добавлен.' })
      setDocForm({ title: '', file_path: '', doc_type: 'regulations' })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleDeleteDocument(documentId: number) {
    if (!confirm('Удалить документ?')) return
    setFeedback(null)
    try {
      await deleteDocument.mutateAsync({ competitionId, documentId })
      setFeedback({ kind: 'success', message: 'Документ удалён.' })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <div className="mt-4 border-t border-steel-dim/30 pt-4">
      <div className="flex flex-col gap-3">
        <textarea
          placeholder="Описание турнира"
          value={form.description ?? ''}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          rows={3}
          className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
        />
        <div className="flex flex-wrap gap-3">
          <input
            placeholder="URL афиши"
            value={form.poster_path ?? ''}
            onChange={(e) => setForm({ ...form, poster_path: e.target.value })}
            className="flex-1 min-w-[200px] rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <input
            placeholder="URL регламента"
            value={form.regulations_doc_path ?? ''}
            onChange={(e) => setForm({ ...form, regulations_doc_path: e.target.value })}
            className="flex-1 min-w-[200px] rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <select
            value={form.location_city_id ?? ''}
            onChange={(e) => setForm({ ...form, location_city_id: e.target.value ? Number(e.target.value) : undefined })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          >
            <option value="">Город: не менять</option>
            {cities.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={handleSave}
          disabled={updateCompetition.isPending}
          className="self-start rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
        >
          Сохранить
        </button>
      </div>

      <p className="text-eyebrow mt-6 text-steel">Документы турнира</p>
      <form onSubmit={handleAddDocument} className="mt-2 flex flex-wrap items-end gap-2">
        <input
          required
          placeholder="Название"
          value={docForm.title}
          onChange={(e) => setDocForm({ ...docForm, title: e.target.value })}
          className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-2 py-1.5 text-xs text-bone focus:border-brass focus:outline-none"
        />
        <input
          required
          placeholder="URL файла"
          value={docForm.file_path}
          onChange={(e) => setDocForm({ ...docForm, file_path: e.target.value })}
          className="flex-1 min-w-[160px] rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-2 py-1.5 text-xs text-bone focus:border-brass focus:outline-none"
        />
        <select
          value={docForm.doc_type ?? ''}
          onChange={(e) => setDocForm({ ...docForm, doc_type: e.target.value })}
          className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-2 py-1.5 text-xs text-bone focus:border-brass focus:outline-none"
        >
          <option value="regulations">регламент</option>
          <option value="protocol">протокол</option>
          <option value="other">другое</option>
        </select>
        <button
          type="submit"
          disabled={createDocument.isPending}
          className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-xs text-steel hover:border-brass hover:text-brass"
        >
          Добавить
        </button>
      </form>

      <div className="mt-3">
        {documents.isLoading && <LoadingState label="Загрузка документов" />}
        {documents.data && documents.data.length === 0 && <p className="text-xs text-steel-dim">Документов пока нет.</p>}
        {documents.data && documents.data.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {documents.data.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2 font-mono text-xs text-steel">
                <span className="truncate">
                  [{d.doc_type ?? 'other'}] {d.title} — {d.file_path}
                </span>
                <button onClick={() => handleDeleteDocument(d.id)} className="flex-shrink-0 text-steel hover:text-danger">
                  удалить
                </button>
              </li>
            ))}
          </ul>
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
