export function formatPhone(value: string): string {
  const body = value.startsWith('8(') ? value.slice(2) : value
  let digits = body.replace(/\D/g, '')
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