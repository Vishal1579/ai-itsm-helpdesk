import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { BookOpen, Check, ClipboardList, LayoutDashboard, MessageSquare, Package } from 'lucide-react'
import { api, type Health, type User } from './api'
import { SessionContext } from './session'
import SelfService from './pages/SelfService'
import Dashboard from './pages/Dashboard'
import Tickets from './pages/Tickets'
import TicketDetail from './pages/TicketDetail'
import Knowledge from './pages/Knowledge'
import Software from './pages/Software'


const NAV = [
  { to: '/', label: 'Get help', icon: MessageSquare, end: true },
  { to: '/dashboard', label: 'ITSM dashboard', icon: LayoutDashboard },
  { to: '/tickets', label: 'Tickets & AI analysis', icon: ClipboardList },
  { to: '/knowledge', label: 'Knowledge base', icon: BookOpen },
  { to: '/software', label: 'Software', icon: Package },
]

export default function App() {
  const [userId, setUserId] = useState(() => {
    try { return localStorage.getItem('itsm.user') ?? 'emp001' } catch { return 'emp001' }
  })
  const [users, setUsers] = useState<User[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [toastMsg, setToastMsg] = useState<string | null>(null)

  useEffect(() => {
    // Keep checking: the backend can take a few seconds to load its models on start-up
    const check = () => {
      api.health().then((h) => { setHealth(h); setHealthError(false) }).catch(() => setHealthError(true))
      api.users().then(setUsers).catch(() => {})
    }
    check()
    const t = window.setInterval(check, 8000)
    return () => window.clearInterval(t)
  }, [])

  useEffect(() => {
    try { localStorage.setItem('itsm.user', userId) } catch { /* storage unavailable */ }
  }, [userId])

  const toast = (msg: string) => {
    setToastMsg(msg)
    window.setTimeout(() => setToastMsg(null), 3200)
  }

  return (
    <SessionContext.Provider value={{ userId, setUserId, users, toast }}>
      <div className="shell">
        <nav className="sidebar" aria-label="Main">
          <div className="brand">
            <div className="brand-mark"><Check size={18} strokeWidth={3} /></div>
            <div>
              <div className="brand-name">Helpdesk</div>
              <div className="brand-sub">IT self-service</div>
            </div>
          </div>
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <Icon size={17} /> <span className={label.length > 12 ? 'label-long' : ''}>{label}</span>
            </NavLink>
          ))}
          <div className="sidebar-foot">
            <div className="field">
              <label htmlFor="user">Signed in as</label>
              <select id="user" className="select" value={userId} onChange={(e) => setUserId(e.target.value)}>
                {(users.length ? users : [{ user_id: 'emp001', name: 'Jordan Lee', role: 'employee' } as User]).map((u) => (
                  <option key={u.user_id} value={u.user_id}>{u.name}{u.role === 'privileged' ? ' (admin)' : ''}</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'grid', gap: 4 }}>
              {healthError && <div className="status-line"><span className="dot warn" />Backend offline on :8000</div>}
              {health && (
                <>
                  <div className="status-line"><span className="dot ok" />{health.database === 'in-memory' ? 'In-memory DB' : 'MongoDB'}</div>
                  <div className="status-line" title={health.llm.model}><span className={`dot ${health.llm.provider === 'extractive' ? 'warn' : 'ok'}`} />{shortModel(health.llm.model)}</div>
                  <div className="status-line"><span className="dot ok" />ServiceNow {health.servicenow.mode}</div>
                </>
              )}
            </div>
          </div>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<SelfService />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/tickets" element={<Tickets />} />
            <Route path="/tickets/:id" element={<TicketDetail />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/software" element={<Software />} />
          </Routes>
        </main>
      </div>
      {toastMsg && <div className="toast" role="status">{toastMsg}</div>}
    </SessionContext.Provider>
  )
}

function shortModel(m: string) {
  return m.includes('/') ? m.split('/')[1] : m
}
