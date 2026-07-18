interface GaugeProps {
  /** Значение в диапазоне [min, max] */
  value: number
  label: string
  sublabel?: string
  size?: number
  accent?: 'brass' | 'rust'
  /** По умолчанию 0..100 (проценты, как раньше — win-rate и т.п.) */
  min?: number
  max?: number
  /** Как отформатировать число в центре циферблата. По умолчанию — "N%". */
  format?: (clamped: number) => string
}

/**
 * Циферблат манометра — сигнатурный элемент айдентики. Используется для
 * читаемых с одного взгляда метрик спортсмена: чем выше "давление", тем
 * ближе стрелка к красной зоне справа, ровно как на приборной панели
 * буровой установки. Диапазон настраиваемый (min/max), поэтому подходит
 * и для процентов (win-rate), и для рейтинга Эло — см. EloRating.tsx.
 */
export function Gauge({
  value,
  label,
  sublabel,
  size = 132,
  accent = 'brass',
  min = 0,
  max = 100,
  format,
}: GaugeProps) {
  const clamped = Math.max(min, Math.min(max, value))
  const pct = (clamped - min) / (max - min)
  // Циферблат — дуга 270°, от -135° до +135°, ноль внизу-слева.
  const angle = -135 + pct * 270
  const r = size / 2 - 10
  const cx = size / 2
  const cy = size / 2
  const displayValue = format ? format(clamped) : `${Math.round(clamped)}%`

  const ticks = Array.from({ length: 11 }, (_, i) => i)
  const accentColor = accent === 'brass' ? 'var(--color-brass)' : 'var(--color-rust)'

  return (
    <div className="flex flex-col items-center gap-2" role="img" aria-label={`${label}: ${displayValue}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r + 6} fill="var(--color-ink-soft)" stroke="rgba(146,160,166,0.18)" />
        {ticks.map((i) => {
          const tAngle = -135 + (i / 10) * 270
          const rad = (tAngle * Math.PI) / 180
          const x1 = cx + Math.cos(rad) * (r - 2)
          const y1 = cy + Math.sin(rad) * (r - 2)
          const x2 = cx + Math.cos(rad) * (r - 10)
          const y2 = cy + Math.sin(rad) * (r - 10)
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="var(--color-steel)"
              strokeWidth={i % 5 === 0 ? 2 : 1}
              opacity={0.7}
            />
          )
        })}
        <line
          x1={cx}
          y1={cy}
          x2={cx + Math.cos((angle * Math.PI) / 180) * (r - 16)}
          y2={cy + Math.sin((angle * Math.PI) / 180) * (r - 16)}
          stroke={accentColor}
          strokeWidth={3}
          strokeLinecap="round"
          style={{ transition: 'all 0.6s cubic-bezier(0.22, 1, 0.36, 1)' }}
        />
        <circle cx={cx} cy={cy} r={5} fill={accentColor} />
        <text
          x={cx}
          y={cy + r * 0.55}
          textAnchor="middle"
          fontFamily="var(--font-display)"
          fontSize={size * (displayValue.length > 4 ? 0.13 : 0.16)}
          fontWeight={700}
          fill="var(--color-bone)"
        >
          {displayValue}
        </text>
      </svg>
      <div className="text-center">
        <div className="text-eyebrow text-steel">{label}</div>
        {sublabel && <div className="font-mono text-xs text-steel-dim">{sublabel}</div>}
      </div>
    </div>
  )
}
