export function FeedbackBanner({ kind, message }: { kind: 'success' | 'error'; message: string }) {
  return (
    <p
      className={`rounded-[var(--radius-rivet)] px-3 py-2 text-sm ${
        kind === 'success' ? 'bg-success/15 text-success' : 'bg-danger/15 text-danger'
      }`}
      role={kind === 'error' ? 'alert' : 'status'}
    >
      {message}
    </p>
  )
}
