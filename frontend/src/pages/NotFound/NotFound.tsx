import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-5 py-28 text-center">
      <svg width="72" height="72" viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="32" cy="32" r="30" fill="var(--color-ink-soft)" stroke="rgba(146,160,166,0.3)" />
        <circle cx="32" cy="32" r="24" fill="none" stroke="var(--color-steel)" strokeWidth="1.5" strokeDasharray="2.5 4.2" opacity="0.5" />
        <path d="M32 32 L18 44" stroke="var(--color-danger)" strokeWidth="4" strokeLinecap="round" />
        <circle cx="32" cy="32" r="4.5" fill="var(--color-brass)" />
      </svg>
      <p className="text-eyebrow mt-6 text-danger">Давление упало до нуля</p>
      <h1 className="mt-2 font-display text-2xl text-bone">Страница не найдена</h1>
      <p className="mt-2 text-steel">Такой страницы нет на сайте федерации.</p>
      <Link
        to="/"
        className="mt-6 rounded-[var(--radius-rivet)] bg-rust px-5 py-3 text-sm font-semibold text-bone hover:bg-rust-dim"
      >
        На главную
      </Link>
    </div>
  )
}
