// Типы зеркалят Pydantic-схемы backend/app/schemas/*.py (группа /api/v1/public).
// Держать в синхроне с бэкендом вручную, пока нет генерации из OpenAPI.

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type Gender = 'male' | 'female'
export type Hand = 'left' | 'right'
export type Medal = 'gold' | 'silver' | 'bronze' | 'none'
export type CompetitionStatus = 'draft' | 'published' | 'in_progress' | 'completed'

export interface AthleteListItem {
  id: number
  full_name: string
  birth_date: string | null
  gender: Gender
  club_name: string | null
  coach_name: string | null
  city_name: string | null
  rank: string | null
  photo_path: string | null
}

export interface AthleteStatistics {
  total_competitions: number
  total_wins: number
  total_losses: number
  win_rate: number
  left_hand_wins: number
  left_hand_losses: number
  right_hand_wins: number
  right_hand_losses: number
  gold_count: number
  silver_count: number
  bronze_count: number
  /** Независимый рейтинг по руке. Общий рейтинг на сайте — elo_combined,
   * (elo_left + elo_right) / 2, посчитан на бэкенде (backend/app/services/elo_engine.py). */
  elo_left: number
  elo_right: number
  elo_combined: number
}

export interface AthleteDetail {
  id: number
  full_name: string
  birth_date: string | null
  gender: Gender
  club_name: string | null
  coach_name: string | null
  city_name: string | null
  region_name: string | null
  country_name: string | null
  rank: string | null
  photo_path: string | null
  bio: string | null
  statistics: AthleteStatistics | null
}

export interface AthleteCompetitionHistoryItem {
  competition_id: number
  competition_name: string
  date: string
  category_name: string
  place: number | null
  medal: Medal
}

export interface AthleteMatchHistoryItem {
  match_id: number
  competition_id: number
  competition_name: string
  category_name: string
  round_name: string | null
  opponent_name: string | null
  is_winner: boolean | null
}

export interface AthleteListParams {
  name?: string
  club_id?: number
  city_id?: number
  coach_id?: number
  age?: number
  weight_category_id?: number
  rank?: string
  gender?: Gender
  page?: number
  page_size?: number
}

export interface CompetitionListItem {
  id: number
  name: string
  date: string
  location_city_name: string | null
  organizer: string | null
  status: CompetitionStatus
  participants_count: number
}

export interface CategoryOut {
  id: number
  name: string
  hand: Hand
}

export interface ParticipantOut {
  athlete_id: number
  athlete_name: string
  category_name: string
  hand: Hand
  weight_at_event: number | null
  club_at_event: string | null
}

export interface CompetitionDetail {
  id: number
  name: string
  date: string
  location_city_name: string | null
  organizer: string | null
  description: string | null
  poster_path: string | null
  regulations_doc_path: string | null
  status: CompetitionStatus
  participants_count: number
  weight_tolerance: number | null
  bracket_system: 'double' | 'single' | null
  format_type: 'combined' | 'separate' | null
  categories: CategoryOut[]
}

export interface ResultOut {
  category_name: string
  place: number | null
  medal: Medal
  athlete_id: number
  athlete_name: string
  club_name: string | null
}

export interface BracketMatchOut {
  id: number
  category_name: string
  bracket: string
  round_name: string | null
  match_order: number
  p1_name: string | null
  p2_name: string | null
  winner_name: string | null
  status: string
}

export interface QueuePairOut {
  match_id: number
  category_name: string
  round_name: string | null
  p1_name: string
  p2_name: string
}

export interface TableQueueOut {
  table_number: number
  current: QueuePairOut | null
  next: QueuePairOut[]
}

export interface CompetitionListParams {
  year?: number
  status?: CompetitionStatus
  page?: number
  page_size?: number
}

export interface ClubListItem {
  id: number
  name: string
  logo_path: string | null
  city_name: string | null
  rating_points: number
  athletes_count: number
}

export interface CoachListItem {
  id: number
  full_name: string
  photo_path: string | null
  club_name: string | null
  athletes_count: number
}

export interface CoachDetail extends CoachListItem {
  bio: string | null
}

export interface NewsListItem {
  id: number
  title: string
  slug: string
  cover_photo_path: string | null
  published_at: string | null
}

export interface NewsDetail extends NewsListItem {
  content: string | null
}

export interface AthleteRankingRow {
  position: number | null
  athlete_id: number
  athlete_name: string
  club_name: string | null
  points: number
  period: string | null
}

export interface ClubRankingRow {
  position: number | null
  club_id: number
  club_name: string
  points: number
  gold_count: number
  silver_count: number
  bronze_count: number
}

export interface City {
  id: number
  name: string
  region_name: string
}

// --- Auth ---------------------------------------------------------------

export type RoleCode = 'super_admin' | 'admin' | 'editor' | 'guest'

export interface AuthUser {
  id: number
  username: string
  email: string
  full_name: string
  is_active: boolean
  role_code: RoleCode
}

// --- Admin: mutation результаты -----------------------------------------
// POST /admin/* -> {id}; PATCH/DELETE /admin/* -> {status}. Полных объектов
// не возвращают — после мутации фронт инвалидирует чтение (React Query).

export interface CreatedRef {
  id: number
}

export interface StatusResult {
  status: string
}

// --- Admin: clubs / coaches ----------------------------------------------
// GET-листинга в /admin нет — читаем список/детали через /public/clubs и
// /public/coaches (см. lib/api.ts), пишем через /admin/*.

export interface ClubInput {
  name: string
  logo_path?: string | null
  description?: string | null
  city_id?: number | null
  founded_year?: number | null
}

export interface CoachInput {
  full_name: string
  photo_path?: string | null
  bio?: string | null
  club_id?: number | null
}

// --- Admin: athletes -------------------------------------------------------

export interface AthleteAdminListItem {
  id: number
  full_name: string
  birth_date: string | null
  gender: Gender
  club_name: string | null
  coach_name: string | null
  city_name: string | null
  rank: string | null
  photo_path: string | null
  is_hidden: boolean
}

export interface AthleteInput {
  full_name: string
  birth_date?: string | null
  gender: Gender
  club_id?: number | null
  coach_id?: number | null
  city_id?: number | null
  region_id?: number | null
  country_id?: number | null
  rank?: string | null
  photo_path?: string | null
  bio?: string | null
}

export interface AthleteUpdateInput extends Partial<AthleteInput> {
  is_hidden?: boolean
}

export interface AthleteStatisticsAdmin extends AthleteStatistics {
  is_manual_override: boolean
  overridden_by: number | null
  overridden_at: string | null
}

export interface AthleteStatisticsUpdateInput {
  total_competitions?: number
  total_wins?: number
  total_losses?: number
  win_rate?: number
  left_hand_wins?: number
  left_hand_losses?: number
  right_hand_wins?: number
  right_hand_losses?: number
  gold_count?: number
  silver_count?: number
  bronze_count?: number
}

// --- Admin: news ------------------------------------------------------------
// GET /admin/news (list, без content) и GET /admin/news/{id} (detail, с
// content) — оба существуют, в отличие от clubs/coaches.

export interface NewsAdminListItem {
  id: number
  title: string
  slug: string
  cover_photo_path: string | null
  is_published: boolean
  published_at: string | null
}

export interface NewsAdminDetail extends NewsAdminListItem {
  content: string | null
}

export interface NewsInput {
  title: string
  slug: string
  content?: string | null
  cover_photo_path?: string | null
  is_published?: boolean
}

// --- Admin: gallery -----------------------------------------------------------
// Альбомы и видео можно создавать, но НЕЛЬЗЯ удалять через API (эндпоинтов
// delete для них нет в backend) — фото удалить можно.

export interface GalleryAlbum {
  id: number
  competition_id: number | null
  title: string | null
  created_at: string
}

export interface GalleryAlbumInput {
  competition_id?: number | null
  title?: string | null
}

export interface GalleryPhoto {
  id: number
  album_id: number | null
  competition_id: number | null
  athlete_id: number | null
  url: string
  caption: string | null
}

export interface GalleryPhotoInput {
  album_id?: number | null
  competition_id?: number | null
  athlete_id?: number | null
  url: string
  caption?: string | null
}

export interface GalleryVideo {
  id: number
  competition_id: number | null
  news_id: number | null
  title: string | null
  url: string
}

export interface GalleryVideoInput {
  competition_id?: number | null
  news_id?: number | null
  title?: string | null
  url: string
}

export interface GalleryDocument {
  id: number
  competition_id: number
  title: string
  file_path: string
  doc_type: string | null
}

export interface GalleryDocumentInput {
  competition_id: number
  title: string
  file_path: string
  doc_type?: string | null
}

// --- Admin: competitions (только информационные поля — whitelisted) -------

export interface CompetitionAdminUpdateInput {
  description?: string | null
  poster_path?: string | null
  regulations_doc_path?: string | null
  location_city_id?: number | null
}
