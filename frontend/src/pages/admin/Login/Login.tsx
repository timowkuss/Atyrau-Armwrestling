import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/features/auth/useAuth'

export function AdminLogin() {
  const { token, user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (token && user) {
    const from = (location.state as { from?: Location })?.from?.pathname ?? '/admin'
    return <Navigate to={from} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(username, password)
      navigate('/admin', { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-5">
      <div className="plate w-full max-w-sm rounded-[var(--radius-rivet)] p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <img src="/brand/logo-armsport.png" alt="Р›РѕРіРѕС‚РёРї С„РµРґРµСЂР°С†РёРё" className="h-10 w-auto" />
          <span className="font-display text-sm font-bold uppercase tracking-wide text-bone">
            Atyrau<span className="text-rust"> Armsport</span>
          </span>
        </div>
        <p className="text-eyebrow mt-6 text-rust">РџР°РЅРµР»СЊ СѓРїСЂР°РІР»РµРЅРёСЏ</p>
        <h1 className="mt-1 font-display text-2xl text-bone">Р’С…РѕРґ</h1>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="username" className="text-eyebrow text-steel">
              Р›РѕРіРёРЅ
            </label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="password" className="text-eyebrow text-steel">
              РџР°СЂРѕР»СЊ
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="rounded-[var(--radius-rivet)] border border-steel-dim bg-ink px-3 py-2 text-sm text-bone focus:border-brass focus:outline-none"
            />
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
          <button
            type="submit"
            disabled={isSubmitting}
            className="mt-2 rounded-[var(--radius-rivet)] bg-rust px-4 py-2.5 text-sm font-semibold text-bone transition-colors hover:bg-rust-dim disabled:opacity-50"
          >
            {isSubmitting ? 'Р’С…РѕРґРёРјвЂ¦' : 'Р’РѕР№С‚Рё'}
          </button>
        </form>
      </div>
    </div>
  )
}
