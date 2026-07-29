/**
 * Просим Cloudinary отдать уже готовый, качественный превью нужного
 * размера — вместо того чтобы грузить оригинал в полном разрешении и
 * сжимать его в браузере (что и давало мутные квадратики в админке).
 *
 * c_fill,g_face — кадрирует под нужные пропорции с фокусом на лицо
 * (если распознано), а не просто по центру.
 * q_auto,f_auto — Cloudinary сам подберёт оптимальные качество и формат
 * (webp/avif) под браузер клиента.
 * *2 к размеру — чтобы фото было чётким на retina-экранах.
 */
export function cloudinaryThumb(url: string | null | undefined, size: number): string | null {
  if (!url) return null
  const marker = '/upload/'
  const idx = url.indexOf(marker)
  if (idx === -1) return url // не Cloudinary URL (старый локальный путь и т.п.) — отдаём как есть
  const px = Math.round(size * 2)
  const transform = `c_fill,g_face,w_${px},h_${px},q_auto,f_auto`
  return url.slice(0, idx + marker.length) + transform + '/' + url.slice(idx + marker.length)
}
