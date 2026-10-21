import { createContext, useContext } from 'react'
import type { User } from './api'

export interface Session { userId: string; setUserId: (id: string) => void; users: User[]; toast: (msg: string) => void }
export const SessionContext = createContext<Session>({ userId: 'emp001', setUserId: () => {}, users: [], toast: () => {} })
export const useSession = () => useContext(SessionContext)
