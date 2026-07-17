import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { adminApi } from '@/lib/adminApi'
import type { GalleryAlbumInput, GalleryPhotoInput, GalleryVideoInput } from '@/types/api'

export function useAdminAlbums() {
  const { token } = useAuth()
  return useQuery({ queryKey: ['admin', 'gallery', 'albums'], queryFn: () => adminApi.gallery.albums.list(token!), enabled: !!token })
}

export function useCreateAlbum() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: GalleryAlbumInput) => adminApi.gallery.albums.create(token!, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'gallery', 'albums'] }),
  })
}

export function useAdminPhotos(albumId?: number) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['admin', 'gallery', 'photos', albumId ?? null],
    queryFn: () => adminApi.gallery.photos.list(token!, albumId ? { album_id: albumId } : undefined),
    enabled: !!token,
  })
}

export function useCreatePhoto() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: GalleryPhotoInput) => adminApi.gallery.photos.create(token!, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'gallery', 'photos'] }),
  })
}

export function useDeletePhoto() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.gallery.photos.remove(token!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'gallery', 'photos'] }),
  })
}

export function useAdminVideos() {
  const { token } = useAuth()
  return useQuery({ queryKey: ['admin', 'gallery', 'videos'], queryFn: () => adminApi.gallery.videos.list(token!), enabled: !!token })
}

export function useCreateVideo() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: GalleryVideoInput) => adminApi.gallery.videos.create(token!, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'gallery', 'videos'] }),
  })
}

export function useDeleteVideo() {
  const { token } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.gallery.videos.remove(token!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'gallery', 'videos'] }),
  })
}
