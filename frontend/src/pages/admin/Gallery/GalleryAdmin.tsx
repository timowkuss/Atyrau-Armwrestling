import { useState } from 'react'
import {
  useAdminAlbums,
  useAdminPhotos,
  useAdminVideos,
  useCreateAlbum,
  useCreatePhoto,
  useCreateVideo,
  useDeletePhoto,
  useDeleteVideo,
} from '@/features/admin/useGalleryAdmin'
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States'
import { FeedbackBanner } from '@/components/admin/FeedbackBanner'
import type { GalleryPhotoInput, GalleryVideoInput } from '@/types/api'

type Tab = 'albums' | 'photos' | 'videos'

export function GalleryAdmin() {
  const [tab, setTab] = useState<Tab>('photos')
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)

  return (
    <div>
      <p className="text-eyebrow text-rust">Медиатека</p>
      <h1 className="mt-2 font-display text-2xl text-bone">Галерея</h1>

      {feedback && (
        <div className="mt-4">
          <FeedbackBanner kind={feedback.kind} message={feedback.message} />
        </div>
      )}

      <div className="mt-6 flex gap-2">
        {(
          [
            ['photos', 'Фото'],
            ['albums', 'Альбомы'],
            ['videos', 'Видео'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`text-eyebrow rounded-[var(--radius-rivet)] px-3 py-1.5 transition-colors ${
              tab === key ? 'bg-petrol-2 text-brass' : 'border border-steel-dim text-steel hover:text-bone'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'albums' && <AlbumsTab onFeedback={setFeedback} />}
        {tab === 'photos' && <PhotosTab onFeedback={setFeedback} />}
        {tab === 'videos' && <VideosTab onFeedback={setFeedback} />}
      </div>
    </div>
  )
}

type Feedback = { kind: 'success' | 'error'; message: string }

function AlbumsTab({ onFeedback }: { onFeedback: (f: Feedback) => void }) {
  const albums = useAdminAlbums()
  const createAlbum = useCreateAlbum()
  const [title, setTitle] = useState('')

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    try {
      await createAlbum.mutateAsync({ title: title || undefined })
      onFeedback({ kind: 'success', message: 'Альбом создан.' })
      setTitle('')
    } catch (err) {
      onFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <div>
      <form onSubmit={handleCreate} className="plate flex flex-wrap items-end gap-3 rounded-[var(--radius-rivet)] p-4">
        <div className="flex flex-1 flex-col gap-1 min-w-[200px]">
          <label className="text-eyebrow text-steel">Название альбома</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={createAlbum.isPending}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
        >
          Создать
        </button>
      </form>
      <p className="mt-2 text-xs text-steel-dim">Удаление альбомов пока недоступно в API — только создание и просмотр.</p>

      <div className="mt-4">
        {albums.isLoading && <LoadingState label="Загрузка альбомов" />}
        {albums.isError && <ErrorState message={(albums.error as Error).message} onRetry={() => albums.refetch()} />}
        {albums.data && albums.data.length === 0 && <EmptyState title="Альбомов пока нет" />}
        {albums.data && albums.data.length > 0 && (
          <ul className="mt-4 flex flex-col gap-2">
            {albums.data.map((a) => (
              <li key={a.id} className="plate rounded-[var(--radius-rivet)] p-3 text-sm text-bone">
                {a.title ?? `Альбом #${a.id}`}{' '}
                <span className="font-mono text-xs text-steel">· {new Date(a.created_at).toLocaleDateString('ru-RU')}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function PhotosTab({ onFeedback }: { onFeedback: (f: Feedback) => void }) {
  const photos = useAdminPhotos()
  const albums = useAdminAlbums()
  const createPhoto = useCreatePhoto()
  const deletePhoto = useDeletePhoto()
  const [form, setForm] = useState<GalleryPhotoInput>({ url: '', caption: '' })

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    try {
      await createPhoto.mutateAsync(form)
      onFeedback({ kind: 'success', message: 'Фото добавлено.' })
      setForm({ url: '', caption: '' })
    } catch (err) {
      onFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleDelete(id: number) {
    if (!confirm('Удалить фото?')) return
    try {
      await deletePhoto.mutateAsync(id)
      onFeedback({ kind: 'success', message: 'Фото удалено.' })
    } catch (err) {
      onFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <div>
      <form onSubmit={handleCreate} className="plate flex flex-wrap items-end gap-3 rounded-[var(--radius-rivet)] p-4">
        <div className="flex flex-1 flex-col gap-1 min-w-[220px]">
          <label className="text-eyebrow text-steel">URL фото</label>
          <input
            required
            value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })}
            placeholder="https://…"
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
        </div>
        <div className="flex flex-1 flex-col gap-1 min-w-[180px]">
          <label className="text-eyebrow text-steel">Подпись</label>
          <input
            value={form.caption ?? ''}
            onChange={(e) => setForm({ ...form, caption: e.target.value })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-eyebrow text-steel">Альбом</label>
          <select
            value={form.album_id ?? ''}
            onChange={(e) => setForm({ ...form, album_id: e.target.value ? Number(e.target.value) : undefined })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          >
            <option value="">без альбома</option>
            {albums.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.title ?? `Альбом #${a.id}`}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={createPhoto.isPending}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
        >
          Добавить
        </button>
      </form>

      <div className="mt-4">
        {photos.isLoading && <LoadingState label="Загрузка фото" />}
        {photos.isError && <ErrorState message={(photos.error as Error).message} onRetry={() => photos.refetch()} />}
        {photos.data && photos.data.length === 0 && <EmptyState title="Фото пока нет" />}
        {photos.data && photos.data.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {photos.data.map((p) => (
              <div key={p.id} className="plate flex items-center gap-3 rounded-[var(--radius-rivet)] p-3">
                <img src={p.url} alt={p.caption ?? ''} className="h-14 w-14 flex-shrink-0 rounded object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-bone">{p.caption ?? '(без подписи)'}</p>
                  <p className="truncate font-mono text-xs text-steel-dim">{p.url}</p>
                </div>
                <button
                  onClick={() => handleDelete(p.id)}
                  className="flex-shrink-0 rounded-[var(--radius-rivet)] border border-steel-dim px-2 py-1 text-xs text-steel hover:border-danger hover:text-danger"
                >
                  Удалить
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function VideosTab({ onFeedback }: { onFeedback: (f: Feedback) => void }) {
  const videos = useAdminVideos()
  const createVideo = useCreateVideo()
  const deleteVideo = useDeleteVideo()
  const [form, setForm] = useState<GalleryVideoInput>({ url: '', title: '' })

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    try {
      await createVideo.mutateAsync(form)
      onFeedback({ kind: 'success', message: 'Видео добавлено.' })
      setForm({ url: '', title: '' })
    } catch (err) {
      onFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  async function handleDelete(id: number) {
    if (!confirm('Удалить видео?')) return
    try {
      await deleteVideo.mutateAsync(id)
      onFeedback({ kind: 'success', message: 'Видео удалено.' })
    } catch (err) {
      onFeedback({ kind: 'error', message: (err as Error).message })
    }
  }

  return (
    <div>
      <form onSubmit={handleCreate} className="plate flex flex-wrap items-end gap-3 rounded-[var(--radius-rivet)] p-4">
        <div className="flex flex-1 flex-col gap-1 min-w-[180px]">
          <label className="text-eyebrow text-steel">Название</label>
          <input
            value={form.title ?? ''}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
        </div>
        <div className="flex flex-1 flex-col gap-1 min-w-[220px]">
          <label className="text-eyebrow text-steel">URL видео (YouTube и т.п.)</label>
          <input
            required
            value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })}
            className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={createVideo.isPending}
          className="rounded-[var(--radius-rivet)] bg-rust px-4 py-2 text-sm font-semibold text-bone hover:bg-rust-dim disabled:opacity-50"
        >
          Добавить
        </button>
      </form>

      <div className="mt-4">
        {videos.isLoading && <LoadingState label="Загрузка видео" />}
        {videos.isError && <ErrorState message={(videos.error as Error).message} onRetry={() => videos.refetch()} />}
        {videos.data && videos.data.length === 0 && <EmptyState title="Видео пока нет" />}
        {videos.data && videos.data.length > 0 && (
          <ul className="mt-4 flex flex-col gap-2">
            {videos.data.map((v) => (
              <li key={v.id} className="plate flex items-center justify-between gap-3 rounded-[var(--radius-rivet)] p-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-bone">{v.title ?? '(без названия)'}</p>
                  <p className="truncate font-mono text-xs text-steel-dim">{v.url}</p>
                </div>
                <button
                  onClick={() => handleDelete(v.id)}
                  className="flex-shrink-0 rounded-[var(--radius-rivet)] border border-steel-dim px-2 py-1 text-xs text-steel hover:border-danger hover:text-danger"
                >
                  Удалить
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
