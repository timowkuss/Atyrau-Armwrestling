import type { DetailedHTMLProps, HTMLAttributes } from 'react'

// @google/model-viewer регистрирует нативный custom element <model-viewer>,
// у него нет собственных React-типов — описываем минимально нужный набор
// атрибутов, чтобы TSX не ругался.
type ModelViewerAttributes = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
  src?: string
  alt?: string
  poster?: string
  'auto-rotate'?: boolean
  'auto-rotate-delay'?: string | number
  'rotation-per-second'?: string
  'camera-controls'?: boolean
  'camera-orbit'?: string
  'camera-target'?: string
  'min-camera-orbit'?: string
  'max-camera-orbit'?: string
  'interaction-prompt'?: 'auto' | 'none' | 'when-focused'
  'shadow-intensity'?: string | number
  'shadow-softness'?: string | number
  'environment-image'?: string
  exposure?: string | number
  'tone-mapping'?: string
  loading?: 'auto' | 'lazy' | 'eager'
  reveal?: 'auto' | 'interaction' | 'manual'
  ar?: boolean
  'disable-zoom'?: boolean
}

declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'model-viewer': ModelViewerAttributes
    }
  }
}

export {}
