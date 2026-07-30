interface GaugeProps {
  value: number
  label: string
  sublabel?: string
  size?: number
  accent?: 'brass' | 'rust'
  min?: number
  max?: number
  format?: (clamped: number) => string
}

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
  const r = size / 2 - 16
  const cx = size / 2
  const cy = size / 2
  const displayValue = format ? format(clamped) : `${Math.round(clamped)}%`

  const strokeWidth = 8
  const arcAngle = 180
  const startAngle = 180
  const endAngle = startAngle + arcAngle

  const polarToCartesian = (angleDeg: number) => {
    const rad = ((angleDeg - 90) * Math.PI) / 180
    return {
      x: cx + r * Math.cos(rad),
      y: cy + r * Math.sin(rad),
    }
  }

  const describeArc = (from: number, to: number) => {
    const start = polarToCartesian(from)
    const end = polarToCartesian(to)
    const large = to - from > 180 ? 1 : 0
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 1 ${end.x} ${end.y}`
  }

  const activeAngle = startAngle + pct * arcAngle
  const trackD = describeArc(startAngle, endAngle)
  const activeD = describeArc(startAngle, Math.min(activeAngle, endAngle))
  const accentColor = accent === 'brass' ? 'var(--color-brass)' : 'var(--color-rust)'

  return (
    <div className="flex flex-col items-center gap-2" role="img" aria-label={`${label}: ${displayValue}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <path d={trackD} fill="none" stroke="rgba(146,160,166,0.12)" strokeWidth={strokeWidth} strokeLinecap="round" />
        <path
          d={activeD}
          fill="none"
          stroke={accentColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          style={{
            transition: 'd 0.8s cubic-bezier(0.22, 1, 0.36, 1)',
            filter: `drop-shadow(0 0 6px ${accentColor})`,
          }}
        />
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          fontFamily="var(--font-display)"
          fontSize={size * (displayValue.length > 4 ? 0.16 : 0.2)}
          fontWeight={700}
          fill="var(--color-bone)"
        >
          {displayValue}
        </text>
        <text
          x={cx}
          y={cy + 14}
          textAnchor="middle"
          fontFamily="var(--font-sans)"
          fontSize={10}
          fill="var(--color-steel-dim)"
        >
          {Math.round(pct * 100)}%
        </text>
      </svg>
      <div className="text-center">
        <div className="text-eyebrow text-steel">{label}</div>
        {sublabel && <div className="font-mono text-xs text-steel-dim">{sublabel}</div>}
      </div>
    </div>
  )
}
