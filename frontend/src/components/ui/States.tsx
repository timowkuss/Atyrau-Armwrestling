import type { ReactNode } from 'react'

export function LoadingState({ label = 'Загрузка данных' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-steel" role="status" aria-live="polite">
      <svg width="40" height="40" viewBox="0 0 40 40" className="animate-spin" style={{ animationDuration: '1.4s' }}>
        <circle cx="20" cy="20" r="16" fill="none" stroke="rgba(146,160,166,0.25)" strokeWidth="3" />
        <path d="M20 4 A16 16 0 0 1 36 20" fill="none" stroke="var(--color-brass)" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <p className="text-eyebrow">{label}</p>
    </div>
  )
}

export function ErrorState({
  title = 'Не удалось загрузить данные',
  message,
  onRetry,
}: {
  title?: string
  message?: string
  onRetry?: () => void
}) {
  return (
    <div className="plate rounded-[var(--radius-rivet)] border-l-4 border-l-danger px-6 py-8 text-center">
      <p className="text-eyebrow text-danger">Сбой</p>
      <h3 className="mt-2 font-display text-lg text-bone">{title}</h3>
      {message && <p className="mt-1 text-sm text-steel">{message}</p>}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-[var(--radius-rivet)] border border-steel-dim px-4 py-2 text-sm font-medium text-bone transition-colors hover:border-brass hover:text-brass"
        >
          Повторить попытку
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, message, action }: { title: string; message?: string; action?: ReactNode }) {
  return (
    <div className="rounded-[var(--radius-rivet)] border border-dashed border-steel-dim px-6 py-14 text-center">
      <h3 className="font-display text-lg text-bone">{title}</h3>
      {message && <p className="mt-1 text-sm text-steel">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
