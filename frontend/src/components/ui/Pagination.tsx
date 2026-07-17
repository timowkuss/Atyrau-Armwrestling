interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}

export function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  if (totalPages <= 1) return null

  return (
    <nav className="mt-8 flex items-center justify-between gap-4" aria-label="Постраничная навигация">
      <button
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className="rounded-[var(--radius-rivet)] border border-steel-dim px-4 py-2 text-sm text-bone transition-colors hover:border-brass hover:text-brass disabled:opacity-30 disabled:hover:border-steel-dim disabled:hover:text-bone"
      >
        ← Назад
      </button>
      <span className="font-mono text-xs text-steel">
        стр. {page} из {totalPages} · {total} всего
      </span>
      <button
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className="rounded-[var(--radius-rivet)] border border-steel-dim px-4 py-2 text-sm text-bone transition-colors hover:border-brass hover:text-brass disabled:opacity-30 disabled:hover:border-steel-dim disabled:hover:text-bone"
      >
        Вперёд →
      </button>
    </nav>
  )
}
