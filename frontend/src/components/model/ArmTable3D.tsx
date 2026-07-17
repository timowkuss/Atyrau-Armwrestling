import { useEffect, useRef, useState } from 'react'
import '@google/model-viewer'

const MODEL_SRC = '/models/armwrestling-table.glb'

/**
 * Настоящая 3D-модель турнирного стола (.glb), медленно вращается на
 * главном экране. Рендерится через <model-viewer> (WebGL/GLTF), обёртка
 * держит фирменные состояния загрузки/ошибки в стиле дизайн-системы.
 */
export function ArmTable3D() {
  const ref = useRef<HTMLElement | null>(null)
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading')

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const handleLoad = () => setStatus('loaded')
    const handleError = () => setStatus('error')

    el.addEventListener('load', handleLoad)
    el.addEventListener('error', handleError)
    return () => {
      el.removeEventListener('load', handleLoad)
      el.removeEventListener('error', handleError)
    }
  }, [])

  if (status === 'error') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="text-eyebrow text-rust">3D-модель недоступна</p>
        <p className="font-mono text-xs text-steel-dim">
          Не удалось загрузить {MODEL_SRC}. Проверьте, что файл лежит в public/models.
        </p>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full">
      {status === 'loading' && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <span className="text-eyebrow animate-pulse text-steel">Загрузка модели…</span>
        </div>
      )}
      <model-viewer
        ref={ref}
        src={MODEL_SRC}
        alt="3D-модель турнирного стола для армрестлинга"
        auto-rotate
        auto-rotate-delay="0"
        rotation-per-second="12deg"
        camera-orbit="45deg 62deg auto"
        camera-target="auto auto auto"
        interaction-prompt="none"
        shadow-intensity="0.7"
        shadow-softness="0.9"
        environment-image="neutral"
        exposure="1.05"
        loading="eager"
        reveal="auto"
        disable-zoom
        style={{ width: '100%', height: '100%', backgroundColor: 'transparent', opacity: status === 'loaded' ? 1 : 0, transition: 'opacity 0.4s ease' }}
      />
    </div>
  )
}
