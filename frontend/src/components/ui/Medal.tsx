import type { Medal as MedalType } from '@/types/api'

const MEDAL_META: Record<MedalType, { label: string; color: string } | null> = {
  gold: { label: '1 место', color: 'var(--color-brass)' },
  silver: { label: '2 место', color: 'var(--color-steel)' },
  bronze: { label: '3 место', color: 'var(--color-rust)' },
  none: null,
}

export function MedalBadge({ medal }: { medal: MedalType }) {
  const meta = MEDAL_META[medal]
  if (!meta) return <span className="font-mono text-xs text-steel-dim">—</span>
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs" style={{ color: meta.color }}>
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
        <circle cx="5" cy="5" r="4.5" fill="currentColor" />
      </svg>
      {meta.label}
    </span>
  )
}
