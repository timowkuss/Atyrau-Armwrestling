import type {
  AthleteCompetitionHistoryItem,
  AthleteDetail,
  AthleteListItem,
  AthleteListParams,
  AthleteMatchHistoryItem,
  AthleteRankingRow,
  City,
  ClubListItem,
  ClubRankingRow,
  CoachDetail,
  CoachListItem,
  CompetitionDetail,
  CompetitionListItem,
  CompetitionListParams,
  NewsDetail,
  NewsListItem,
  Page,
  ResultOut,
} from '@/types/api'

// В десктоп-приложении бизнес-логика (DoubleEliminationEngine и т.д.) не
// трогается — этот клиент касается только нового публичного read-only слоя
// FastAPI (см. ARCHITECTURE.md §4.1), который сайт использует для чтения
// единой центральной базы.
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api/v1'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

export function buildQuery(params: object | undefined): string {
  if (!params) return ''
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

async function request<T>(path: string, params?: object): Promise<T> {
  const url = `${API_BASE_URL}${path}${buildQuery(params)}`
  let res: Response
  try {
    res = await fetch(url, { headers: { Accept: 'application/json' } })
  } catch {
    throw new ApiError(0, 'Не удалось связаться с сервером. Проверьте подключение.')
  }
  if (!res.ok) {
    let detail = `Ошибка запроса (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // тело не JSON — оставляем сообщение по умолчанию
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  athletes: {
    list: (params?: AthleteListParams) => request<Page<AthleteListItem>>('/public/athletes', params),
    get: (id: number) => request<AthleteDetail>(`/public/athletes/${id}`),
    history: (id: number) => request<AthleteCompetitionHistoryItem[]>(`/public/athletes/${id}/history`),
    matches: (id: number) => request<AthleteMatchHistoryItem[]>(`/public/athletes/${id}/matches`),
  },
  competitions: {
    list: (params?: CompetitionListParams) => request<Page<CompetitionListItem>>('/public/competitions', params),
    get: (id: number) => request<CompetitionDetail>(`/public/competitions/${id}`),
    results: (id: number) => request<ResultOut[]>(`/public/competitions/${id}/results`),
    photos: (id: number) => request<import('@/types/api').GalleryPhoto[]>(`/public/competitions/${id}/photos`),
  },
  news: {
    list: (params?: { page?: number; page_size?: number }) => request<Page<NewsListItem>>('/public/news', params),
    get: (slug: string) => request<NewsDetail>(`/public/news/${slug}`),
  },
  rankings: {
    athletes: (params?: { period?: string; gender?: string }) =>
      request<AthleteRankingRow[]>('/public/rankings/athletes', params),
    clubs: () => request<ClubRankingRow[]>('/public/rankings/clubs'),
  },
  clubs: {
    list: (params?: { city_id?: number; page?: number; page_size?: number }) =>
      request<Page<ClubListItem>>('/public/clubs', params),
  },
  coaches: {
    list: (params?: { club_id?: number; page?: number; page_size?: number }) =>
      request<Page<CoachListItem>>('/public/coaches', params),
    get: (id: number) => request<CoachDetail>(`/public/coaches/${id}`),
  },
  reference: {
    cities: () => request<City[]>('/public/reference/cities'),
  },
  // Примечание: /public/home/summary описан в ARCHITECTURE.md §4.1, но ещё
  // не реализован в backend (stage 3 отдаёт только athletes/clubs/coaches/
  // competitions). Главная страница поэтому пока собирает сводку сама —
  // из /public/competitions и /public/athletes. Когда summary появится на
  // бэке, эту точку удобно заменить одним вызовом.
}
