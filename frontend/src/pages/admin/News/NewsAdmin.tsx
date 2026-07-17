import { useState } from 'react'
import { useCreateNews, useAdminNewsDetail, useAdminNewsList, useDeleteNews, useUpdateNews } from '@/features/admin/useNewsAdmin'
import { LoadingState, ErrorState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import type { NewsInput } from '@/types/api'

const EMPTY_FORM: NewsInput = { title: '', slug: '', content: '', is_published: false }

function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-zа-яё0-9\s-]/gi, '')
    .trim()
    .replace(/\s+/g, '-')
}

export function NewsAdmin() {
  const news = useAdminNewsList()
  const createNews = useCreateNews()
  const deleteNews = useDeleteNews()

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<NewsInput>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setFeedback(null)
    try {
      await createNews.mutateAsync(form)
      setFeedback({ kind: 'success', message: `Новость «${form.title}» создана.` })
      setForm(EMPTY_FORM)
      setShowCreate(false)
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleDelete(id: number, title: string) {
    if (!confirm(`Удалить новость «${title}»?`)) return
    setFeedback(null)
    try {
      await deleteNews.mutateAsync(id)
      setFeedback({ kind: 'success', message: `«${title}» удалена.` })
    } catch (err) {
      setFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-eyebrow text-rust">Публикации федерации</p>
          <h1 className="mt-2 font-display text-2xl text-bone">Новости</h1>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim"
        >
          {showCreate ? 'Отмена' : '+ Новая новость'}
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
            placeholder="Заголовок"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value, slug: form.slug || slugify(e.target.value) })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <input
            required
            placeholder="slug (латиницей, для URL)"
            value={form.slug}
            onChange={(e) => setForm({ ...form, slug: e.target.value })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 font-mono text-sm text-bone focus:border-brass focus:outline-none"
          />
          <textarea
            placeholder="Текст новости"
            value={form.content ?? ''}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            rows={5}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
          <label className="flex items-center gap-2 text-sm text-steel">
            <input
              type="checkbox"
              checked={form.is_published ?? false}
              onChange={(e) => setForm({ ...form, is_published: e.target.checked })}
            />
            Опубликовать сразу
          </label>
          <button
            type="submit"
            disabled={createNews.isPending}
            className="self-start rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
          >
            {createNews.isPending ? 'Сохранение…' : 'Создать'}
          </button>
        </form>
      )}

      <div className="mt-6">
        {news.isLoading && <LoadingState label="Загрузка новостей" />}
        {news.isError && <ErrorState message={(news.error as Error).message} onRetry={() => news.refetch()} />}
        {news.data && (
          <ul className="flex flex-col gap-3">
            {news.data.map((n) =>
              editingId === n.id ? (
                <NewsEditRow key={n.id} id={n.id} onDone={() => setEditingId(null)} onFeedback={setFeedback} />
              ) : (
                <li key={n.id} className="plate flex items-center justify-between gap-4 rounded-[var(--radius-rivet)] p-4">
                  <div>
                    <p className="flex items-center gap-2 font-display text-base text-bone">
                      {n.title}
                      <span
                        className={`text-eyebrow rounded-[var(--radius-rivet)] px-2 py-0.5 ${
                          n.is_published ? 'bg-success/15 text-success' : 'bg-steel-dim/20 text-steel'
                        }`}
                      >
                        {n.is_published ? 'опубликовано' : 'черновик'}
                      </span>
                    </p>
                    <p className="font-mono text-xs text-steel">/{n.slug}</p>
                  </div>
                  <div className="flex flex-shrink-0 gap-2">
                    <button
                      onClick={() => setEditingId(n.id)}
                      className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-brass hover:text-brass"
                    >
                      Изменить
                    </button>
                    <button
                      onClick={() => handleDelete(n.id, n.title)}
                      className="rounded-[var(--radius-rivet)] border border-steel-dim px-3 py-1.5 text-sm text-steel hover:border-danger hover:text-danger"
                    >
                      Удалить
                    </button>
                  </div>
                </li>
              ),
            )}
          </ul>
        )}
      </div>
    </div>
  )
}

function NewsEditRow({
  id,
  onDone,
  onFeedback,
}: {
  id: number
  onDone: () => void
  onFeedback: (f: { kind: 'success' | 'error'; message: string }) => void
}) {
  const detail = useAdminNewsDetail(id)
  const updateNews = useUpdateNews()
  const [form, setForm] = useState<Partial<NewsInput>>({})

  if (detail.isLoading) return <li className="plate rounded-[var(--radius-rivet)] p-4"><LoadingState label="Загрузка новости" /></li>
  if (detail.isError || !detail.data)
    return (
      <li className="plate rounded-[var(--radius-rivet)] p-4">
        <ErrorState message={(detail.error as Error)?.message} onRetry={() => detail.refetch()} />
      </li>
    )

  const n = detail.data

  async function handleSave() {
    try {
      await updateNews.mutateAsync({ id, payload: form })
      onFeedback({ kind: 'success', message: 'Новость обновлена.' })
      onDone()
    } catch (err) {
      onFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <li className="plate flex flex-col gap-3 rounded-[var(--radius-rivet)] p-4">
      <input
        defaultValue={n.title}
        onChange={(e) => setForm({ ...form, title: e.target.value })}
        className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
      />
      <textarea
        defaultValue={n.content ?? ''}
        onChange={(e) => setForm({ ...form, content: e.target.value })}
        rows={5}
        className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
      />
      <label className="flex items-center gap-2 text-sm text-steel">
        <input
          type="checkbox"
          defaultChecked={n.is_published}
          onChange={(e) => setForm({ ...form, is_published: e.target.checked })}
        />
        Опубликовано
      </label>
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={updateNews.isPending}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
        >
          Сохранить
        </button>
        <button onClick={onDone} className="rounded-[var(--radius-rivet)] border border-steel-dim px-4 py-2 text-sm text-steel hover:text-bone">
          Отмена
        </button>
      </div>
    </li>
  )
}
