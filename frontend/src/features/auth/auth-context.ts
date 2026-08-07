import { createContext } from 'react'
import type { AuthUser } from '@/types/api'

export interface AuthContextValue {
  token: string | null
  user: AuthUser | null
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
