export function formatPhone(value: string): string {
  // фиксированный префикс "8(" не считаем частью набираемых цифр
  const body = value.startsWith('8(') ? value.slice(2) : value
  let digits = body.replace(/\D/g, '')
  // если вставили полный 11-значный номер (8/7) — отбросить префикс
  if (digits.length === 11 && (digits[0] === '8' || digits[0] === '7')) {
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

import type React from 'react'

/** Только цифры, максимум `max` штук. */
export function onlyDigits(value: string, max: number): string {
  return value.replace(/\D/g, '').slice(0, max)
}

/** Блокирует вставку любых символов, кроме цифр (служебные клавиши пропускаются). */
export function blockNonDigits(e: React.KeyboardEvent<HTMLInputElement>): void {
  if (e.ctrlKey || e.metaKey || e.altKey) return
  if (e.key.length === 1 && !/\d/.test(e.key)) {
    e.preventDefault()
  }
}

/** Не даёт стереть фиксированный префикс «8(» у телефона. */
export function blockPhonePrefix(e: React.KeyboardEvent<HTMLInputElement>): void {
  if (e.ctrlKey || e.metaKey) return
  const el = e.currentTarget
  const selStart = el.selectionStart ?? 0
  const selEnd = el.selectionEnd ?? 0
  if (e.key === 'Backspace' && selEnd <= 2) {
    e.preventDefault()
  } else if (e.key === 'Delete' && selStart < 2) {
    e.preventDefault()
  }
}