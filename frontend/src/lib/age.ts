export function age(birthDate: string | null | undefined): number | null {
  if (!birthDate) return null
  const b = new Date(birthDate)
  if (Number.isNaN(b.getTime())) return null
  const diff = Date.now() - b.getTime()
  return Math.floor(diff / (365.25 * 24 * 60 * 60 * 1000))
}
