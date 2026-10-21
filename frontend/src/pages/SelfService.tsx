import { useEffect, useRef, useState } from 'react'
import { Send, Sparkles } from 'lucide-react'
import { api, INTENT_LABEL, type ChatResponse, type Ticket } from '../api'
import { useSession } from '../session'
import { Markdown } from '../components/Markdown'
import { AnalysisPanel } from '../components/AnalysisPanel'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  response?: ChatResponse
}

const SUGGESTIONS = [
  'I cannot connect to VPN since this morning. Authentication keeps failing.',
  'My password has expired.',
  'How do I troubleshoot Outlook synchronization?',
  'I need Visual Studio Code installed on my laptop.',
  'What is the cafeteria menu for Friday?',
]

const GREETING: Message = {
  id: 'hello',
  role: 'assistant',
  text: "Hi, I'm the IT helpdesk assistant. Describe a problem, ask a how-to question or request software. I can fix common issues myself and log anything else in ServiceNow for the right team.",
}

export default function SelfService() {
  const { userId, users, toast } = useSession()
  const [tab, setTab] = useState<'chat' | 'form'>('chat')
  const [messages, setMessages] = useState<Message[]>([GREETING])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string>()
  const [selected, setSelected] = useState<Ticket | null>(null)
  const [animateId, setAnimateId] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const user = users.find((u) => u.user_id === userId)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  // Live status for provisioning requests
  useEffect(() => {
    if (!selected || !['provisioning', 'awaiting_approval'].includes(selected.status)) return
    const t = window.setInterval(async () => {
      try { setSelected(await api.ticket(selected.ticket_id)) } catch { /* keep last state */ }
    }, 2000)
    return () => window.clearInterval(t)
  }, [selected])

  const pushResponse = (res: ChatResponse) => {
    const id = crypto.randomUUID()
    setMessages((m) => [...m, { id, role: 'assistant', text: res.reply, response: res }])
    setSelected(res.ticket)
    setAnimateId(res.ticket.ticket_id)
  }

  const send = async (text: string) => {
    const message = text.trim()
    if (!message || busy) return
    setInput('')
    setError(null)
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', text: message }])
    setBusy(true)
    try {
      const res = await api.chat(message, userId, sessionId)
      setSessionId(res.session_id)
      pushResponse(res)
    } catch (e) {
      setError(`The helpdesk service didn't respond (${(e as Error).message}). Check the backend is running on port 8000, then try again.`)
    } finally {
      setBusy(false)
    }
  }

  const escalate = async (original: ChatResponse) => {
    setBusy(true)
    try {
      const res = await api.escalate(original.ticket.ticket_id)
      const response: ChatResponse = { ...original, reply: res.reply, ticket: res.ticket, actions: [], escalated: true, intent: 'incident' }
      setMessages((m) => [
        ...m.map((msg) => (msg.response?.ticket.ticket_id === res.ticket.ticket_id ? { ...msg, response: { ...msg.response, ticket: res.ticket } } : msg)),
        { id: crypto.randomUUID(), role: 'assistant', text: res.reply, response },
      ])
      setSelected(res.ticket)
      toast(`Ticket ${res.ticket.servicenow?.number} created`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Get IT help</h1>
          <p>Hi {user?.name.split(' ')[0] ?? 'there'}. Ask a question, report a problem or request software. The panel on the right shows exactly what the AI decided and why.</p>
        </div>
      </div>

      <div className="service-grid">
        <div className="panel chat">
          <div className="tabs" role="tablist">
            <button className="tab" role="tab" aria-selected={tab === 'chat'} onClick={() => setTab('chat')}>Chat with the assistant</button>
            <button className="tab" role="tab" aria-selected={tab === 'form'} onClick={() => setTab('form')}>Submit a request</button>
          </div>

          {tab === 'chat' ? (
            <>
              <div className="messages" ref={listRef} aria-live="polite">
                {messages.map((m) => (
                  <div key={m.id} className={`msg ${m.role}${m.response && selected?.ticket_id === m.response.ticket.ticket_id ? ' selected' : ''}`}>
                    <div
                      className="msg-bubble"
                      onClick={() => m.response && setSelected(m.response.ticket)}
                      style={{ cursor: m.response ? 'pointer' : undefined }}
                    >
                      <Markdown text={m.text} />
                    </div>
                    {m.response && (
                      <div className="msg-meta">
                        <span className="tag">{INTENT_LABEL[m.response.intent]}</span>
                        {m.response.ticket.resolved_by === 'ai' && <span className="tag pine">Resolved by AI</span>}
                        {m.response.ticket.escalated && <span className="tag p2">Escalated</span>}
                        {m.response.ticket.servicenow && <span className="code faint">{m.response.ticket.servicenow.number}</span>}
                      </div>
                    )}
                    {m.response && m.response.actions.length > 0 && !m.response.ticket.escalated && (
                      <div className="msg-actions">
                        {m.response.actions.map((a) => (
                          <button key={a.type} className="btn small" disabled={busy} onClick={() => escalate(m.response!)}>{a.label}</button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {busy && <div className="msg assistant"><div className="msg-bubble typing" aria-label="Assistant is working"><span /><span /><span /></div></div>}
              </div>
              <div className="composer">
                {error && <div className="error">{error}</div>}
                {messages.length < 3 && (
                  <div className="suggestions">
                    {SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>{s}</button>)}
                  </div>
                )}
                <form onSubmit={(e) => { e.preventDefault(); send(input) }}>
                  <input
                    className="input"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Describe your issue or question"
                    aria-label="Message"
                    maxLength={2000}
                  />
                  <button className="btn primary" type="submit" disabled={busy || input.trim().length < 2}><Send size={16} /> Send</button>
                </form>
              </div>
            </>
          ) : (
            <RequestForm onDone={(res) => { pushResponse(res); setMessages((m) => [...m.slice(0, -1), { id: crypto.randomUUID(), role: 'user', text: res.ticket.description }, m[m.length - 1]]); setTab('chat') }} />
          )}
        </div>

        <aside className="panel analysis" aria-label="AI analysis">
          {selected ? (
            <AnalysisPanel ticket={selected} animate={animateId === selected.ticket_id} />
          ) : (
            <div className="empty">
              <Sparkles size={22} color="var(--pine)" />
              <h3>What the AI decided</h3>
              <p className="small" style={{ maxWidth: '36ch' }}>
                Send a message to see its intent, category, priority, confidence, the knowledge it used, any automation it ran and the ServiceNow record.
              </p>
            </div>
          )}
        </aside>
      </div>
    </>
  )
}

function RequestForm({ onDone }: { onDone: (res: ChatResponse) => void }) {
  const { userId } = useSession()
  const [type, setType] = useState('auto')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onDone(await api.submitTicket(description, userId, type))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} style={{ padding: 20, display: 'grid', gap: 16, alignContent: 'start', flex: 1 }}>
      <p className="muted small">Prefer a form? Describe what you need and the AI fills in the category, priority and assignment group for you.</p>
      <label className="field">
        <span>Request type</span>
        <select className="select" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="auto">Let the AI decide</option>
          <option value="incident">Something is broken (incident)</option>
          <option value="service_request">I need something (service request)</option>
        </select>
      </label>
      <label className="field">
        <span>Description</span>
        <textarea className="textarea" rows={6} value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder="For example: The shared Finance drive shows access denied since this morning." required minLength={5} />
      </label>
      {error && <div className="error">{error}</div>}
      <div><button className="btn primary" disabled={busy || description.trim().length < 5}>{busy ? 'Submitting…' : 'Submit request'}</button></div>
    </form>
  )
}
