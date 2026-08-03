export function formatPhone(value: string): string {
  let digits = value.replace(/\D/g, '')
  // Если вставили полный 11-значный номер (начинается с 8/7) — отбросить префикс.
  if (digits.length > 10 && (digits[0] === '8' || digits[0] === '7')) {
    digits = digits.slice(1)
  }
  digits = digits.slice(0, 10)

  let result = '8('
  if (digits.length <= 3) {
    result += digits
  } else if (digits.length <= 6) {
    result = `8(${digits.slice(0, 3)})${digits.slice(3)}`
  } else if (digits.length <= 8) {
    result = `8(${digits.slice(0, 3)})${digits.slice(3, 6)}-${digits.slice(6)}`
  } else {
    result = `8(${digits.slice(0, 3)})${digits.slice(3, 6)}-${digits.slice(6, 8)}-${digits.slice(8)}`
  }
  return result
}

/** Форматирует поле при вводе и не даёт допечатать больше 10 цифр. */
export function formatPhoneChange(prev: string | null | undefined, next: string): string {
  const prevDigits = (prev ?? '').replace(/\D/g, '').length
  const nextDigits = next.replace(/\D/g, '').length
  // в заполненном виде в строке ровно 11 цифровых символов (префикс "8" + 10 набираемых)
  if (prevDigits >= 11 && nextDigits > prevDigits) {
    return prev ?? '8('
  }
  return formatPhone(next)
}