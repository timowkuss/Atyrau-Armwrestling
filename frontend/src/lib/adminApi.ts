import { API_BASE_URL, ApiError, buildQuery } from '@/lib/api'
import type {
  AthleteAdminListItem,
  AthleteInput,
  AthleteStatisticsAdmin,
  AthleteStatisticsUpdateInput,
  AthleteUpdateInput,
  ClubInput,
  CoachInput,
  CompetitionAdminUpdateInput,
  CompetitionDetail,
  CreatedRef,
  GalleryAlbum,
  GalleryAlbumInput,
  GalleryDocument,
  GalleryDocumentInput,
  GalleryPhoto,
  GalleryPhotoInput,
  GalleryVideo,
  GalleryVideoInput,
  NewsAdminDetail,
  NewsAdminListItem,
  NewsInput,
  StatusResult,
} from '@/types/api'

async function authedRequest<T>(
  token: string,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
  params?: object,
): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}${buildQuery(params)}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Не удалось связаться с сервером. Проверьте подключение.')
  }

  if (res.status === 204) return undefined as T

  if (!res.ok) {
    let detail = `Ошибка запроса (${res.status})`
    try {
      const problem = await res.json()
      if (typeof problem?.detail === 'string') {
        detail = problem.detail
      } else if (Array.isArray(problem?.detail)) {
        // Ошибка валидации Pydantic (422), в т.ч. "лишнее поле не разрешено"
        // от CompetitionAdminUpdate (extra="forbid", см. ARCHITECTURE.md §6).
        detail = problem.detail
          .map((e: { loc?: string[]; msg?: string }) => `${e.loc?.slice(1).join('.')}: ${e.msg}`)
          .join('; ')
      }
    } catch {
      // тело не JSON
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const adminApi = {
  // Клубы/тренеры: GET-листинга в /admin нет — читать через api.clubs /
  // api.coaches (public), писать здесь.
  clubs: {
    create: (token: string, payload: ClubInput) =>
      authedRequest<CreatedRef>(token, 'POST', '/admin/clubs', payload),
    update: (token: string, id: number, payload: Partial<ClubInput>) =>
      authedRequest<StatusResult>(token, 'PATCH', `/admin/clubs/${id}`, payload),
    remove: (token: string, id: number) => authedRequest<StatusResult>(token, 'DELETE', `/admin/clubs/${id}`),
  },
  coaches: {
    create: (token: string, payload: CoachInput) =>
      authedRequest<CreatedRef>(token, 'POST', '/admin/coaches', payload),
    update: (token: string, id: number, payload: Partial<CoachInput>) =>
      authedRequest<StatusResult>(token, 'PATCH', `/admin/coaches/${id}`, payload),
    remove: (token: string, id: number) => authedRequest<StatusResult>(token, 'DELETE', `/admin/coaches/${id}`),
  },
  athletes: {
    list: (token: string, name?: string) =>
      authedRequest<AthleteAdminListItem[]>(token, 'GET', '/admin/athletes', undefined, { name }),
    create: (token: string, payload: AthleteInput) =>
      authedRequest<CreatedRef>(token, 'POST', '/admin/athletes', payload),
    update: (token: string, id: number, payload: AthleteUpdateInput) =>
      authedRequest<StatusResult>(token, 'PATCH', `/admin/athletes/${id}`, payload),
    remove: (token: string, id: number) => authedRequest<StatusResult>(token, 'DELETE', `/admin/athletes/${id}`),
    getStatistics: (token: string, id: number) =>
      authedRequest<AthleteStatisticsAdmin>(token, 'GET', `/admin/athletes/${id}/statistics`),
    updateStatistics: (token: string, id: number, payload: AthleteStatisticsUpdateInput) =>
      authedRequest<AthleteStatisticsAdmin>(token, 'PATCH', `/admin/athletes/${id}/statistics`, payload),
    recalculateStatistics: (token: string, id: number) =>
      authedRequest<StatusResult>(token, 'POST', `/admin/athletes/${id}/statistics/recalculate`),
  },
  news: {
    list: (token: string) => authedRequest<NewsAdminListItem[]>(token, 'GET', '/admin/news'),
    get: (token: string, id: number) => authedRequest<NewsAdminDetail>(token, 'GET', `/admin/news/${id}`),
    create: (token: string, payload: NewsInput) => authedRequest<CreatedRef>(token, 'POST', '/admin/news', payload),
    update: (token: string, id: number, payload: Partial<NewsInput>) =>
      authedRequest<StatusResult>(token, 'PATCH', `/admin/news/${id}`, payload),
    remove: (token: string, id: number) => authedRequest<StatusResult>(token, 'DELETE', `/admin/news/${id}`),
  },
  gallery: {
    albums: {
      list: (token: string) => authedRequest<GalleryAlbum[]>(token, 'GET', '/admin/gallery/albums'),
      create: (token: string, payload: GalleryAlbumInput) =>
        authedRequest<CreatedRef>(token, 'POST', '/admin/gallery/albums', payload),
      // Удаления альбомов в backend нет (только create/list).
    },
    photos: {
      list: (token: string, params?: { album_id?: number; competition_id?: number }) =>
        authedRequest<GalleryPhoto[]>(token, 'GET', '/admin/gallery/photos', undefined, params),
      create: (token: string, payload: GalleryPhotoInput) =>
        authedRequest<CreatedRef>(token, 'POST', '/admin/gallery/photos', payload),
      remove: (token: string, id: number) => authedRequest<StatusResult>(token, 'DELETE', `/admin/gallery/photos/${id}`),
    },
    videos: {
      list: (token: string) => authedRequest<GalleryVideo[]>(token, 'GET', '/admin/gallery/videos'),
      create: (token: string, payload: GalleryVideoInput) =>
        authedRequest<CreatedRef>(token, 'POST', '/admin/gallery/videos', payload),
      remove: (token: string, id: number) => authedRequest<StatusResult>(token, 'DELETE', `/admin/gallery/videos/${id}`),
    },
  },
  competitions: {
    list: (token: string) => authedRequest<CompetitionDetail[]>(token, 'GET', '/admin/competitions'),
    update: (token: string, id: number, payload: CompetitionAdminUpdateInput) =>
      authedRequest<StatusResult>(token, 'PATCH', `/admin/competitions/${id}`, payload),
    documents: {
      list: (token: string, competitionId: number) =>
        authedRequest<GalleryDocument[]>(token, 'GET', `/admin/competitions/${competitionId}/documents`),
      create: (token: string, competitionId: number, payload: GalleryDocumentInput) =>
        authedRequest<CreatedRef>(token, 'POST', `/admin/competitions/${competitionId}/documents`, payload),
      remove: (token: string, competitionId: number, documentId: number) =>
        authedRequest<StatusResult>(token, 'DELETE', `/admin/competitions/${competitionId}/documents/${documentId}`),
    },
  },
}
