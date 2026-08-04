export function age(birthDate: string | null | undefined): number | null {
  if (!birthDate) return null
  const b = new Date(birthDate)
  if (Number.isNaN(b.getTime())) return null
  const diff = Date.now() - b.getTime()
  return Math.floor(diff / (365.25 * 24 * 60 * 60 * 1000))
}

export function yearsWord(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'год'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'года'
  return 'лет'
}

export function ageText(birthDate: string | null | undefined): string | null {
  const a = age(birthDate)
  if (a === null) return null
  return `${a} ${yearsWord(a)}`
}
