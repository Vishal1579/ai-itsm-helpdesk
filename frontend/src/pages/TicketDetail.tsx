import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, FilePlus2 } from 'lucide-react'
import { api, timeAgo, type SnRecord, type Ticket } from '../api'
import { useSession } from '../session'
import { AnalysisPanel } from '../components/AnalysisPanel'
import { Markdown } from '../components/Markdown'

export default function TicketDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { toast } = useSession()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [snRecord, setSnRecord] = useState<SnRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const t = await api.ticket(id!)
      setTicket(t)
      if (t.servicenow?.table === 'incident') setSnRecord(await api.snIncident(t.servicenow.number))
      else setSnRecord(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!ticket || !['provisioning', 'awaiting_approval'].includes(ticket.status)) return
    const t = window.setInterval(load, 2000)
    return () => window.clearInterval(t)
  }, [ticket, load])

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try {
      await fn()
      toast(done)
      setNote('')
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const draftArticle = async () => {
    setBusy(true)
    try {
      const d = await api.draftFromTicket(ticket!.ticket_id)
      sessionStorage.setItem('itsm.kbDraft', JSON.stringify(d))
      navigate('/knowledge?draft=1')
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  if (error) return <div className="error">{error}</div>
  if (!ticket) return <p className="muted">Loading ticket…</p>
  const isIncident = ticket.servicenow?.table === 'incident'
  const closed = ['resolved', 'closed'].includes(ticket.status)

  return (
    <>
      <Link to="/tickets" className="row small muted" style={{ gap: 4, marginBottom: 14, textDecoration: 'none' }}><ArrowLeft size={14} /> All tickets</Link>
      <div className="page-head">
        <div>
          <h1>{ticket.analysis.summary}</h1>
          <p>
            <span className="code">{ticket.ticket_id}</span>, raised by {ticket.user_name} via {ticket.channel} {timeAgo(ticket.created_at)}
          </p>
        </div>
        <div className="row">
          {!isIncident && !closed && ticket.type === 'knowledge' && (
            <button className="btn" disabled={busy} onClick={() => act(() => api.escalate(ticket.ticket_id), 'Escalated to the Service Desk')}>Escalate to a person</button>
          )}
          <button className="btn" disabled={busy} onClick={draftArticle}><FilePlus2 size={15} /> Draft KB article</button>
        </div>
      </div>

      <div className="detail-grid">
        <div className="stack">
          <div className="panel panel-pad" style={{ display: 'grid', gap: 10 }}>
            <h2>What the employee said</h2>
            <p style={{ fontSize: '1.05rem' }}>“{ticket.description}”</p>
          </div>

          {ticket.rag?.answer && (
            <div className="panel panel-pad" style={{ display: 'grid', gap: 10 }}>
              <h2>{ticket.rag.grounded ? 'Answer from the knowledge base' : 'Response'}</h2>
              <Markdown text={ticket.rag.answer} />
            </div>
          )}

          {snRecord && (
            <div className="panel">
              <div className="panel-head"><h2>ServiceNow record</h2><span className="code">{snRecord.number}</span></div>
              <div className="panel-pad" style={{ display: 'grid', gap: 16 }}>
                <dl className="kv">
                  {['short_description', 'state_label', 'priority', 'impact', 'urgency', 'category', 'subcategory', 'assignment_group', 'caller_id', 'contact_type', 'close_code', 'close_notes']
                    .filter((k) => snRecord[k])
                    .map((k) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{String(snRecord[k])}</dd></div>)}
                </dl>
                {(snRecord.work_notes_history?.length ?? 0) > 0 && (
                  <div style={{ display: 'grid', gap: 8 }}>
                    <h3>Work notes</h3>
                    {snRecord.work_notes_history!.map((n, i) => (
                      <div key={i} className="sunk small" style={{ padding: '9px 12px' }}><div className="faint">{timeAgo(n.at)}</div>{n.note}</div>
                    ))}
                  </div>
                )}
                {!closed && (
                  <form className="row" style={{ alignItems: 'stretch' }} onSubmit={(e) => { e.preventDefault(); act(() => api.updateTicket(ticket.ticket_id, { work_note: note }), 'Work note added in ServiceNow') }}>
                    <input className="input" style={{ flex: 1, minWidth: 200 }} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a work note (synced to ServiceNow)" />
                    <button className="btn" disabled={busy || !note.trim()}>Add note</button>
                    <button type="button" className="btn primary" disabled={busy} onClick={() => act(() => api.updateTicket(ticket.ticket_id, { status: 'resolved', work_note: note || 'Resolved by analyst' }), 'Incident resolved in ServiceNow')}>Resolve incident</button>
                  </form>
                )}
              </div>
            </div>
          )}

          <div className="panel">
            <div className="panel-head"><h2>Audit trail</h2><span className="small faint">{ticket.audit?.length ?? 0} entries</span></div>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Result</th></tr></thead>
                <tbody>
                  {ticket.audit?.map((a) => (
                    <tr key={a.audit_id} className="audit-row">
                      <td className="faint" style={{ whiteSpace: 'nowrap' }}>{new Date(a.timestamp).toLocaleTimeString()}</td>
                      <td>{a.actor}</td>
                      <td className="code">{a.action}</td>
                      <td><span className={`tag ${a.status === 'success' ? 'pine' : 'p2'}`}>{a.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="stack">
          <aside className="panel analysis" style={{ position: 'static', maxHeight: 'none' }}>
            <AnalysisPanel ticket={ticket} showLink={false} />
          </aside>
          <div className="panel panel-pad" style={{ display: 'grid', gap: 12 }}>
            <h2>Timeline</h2>
            <ul className="timeline">
              {ticket.timeline.map((e, i) => (
                <li key={i}><span className="faint">{new Date(e.at).toLocaleTimeString()}</span><span><strong style={{ fontWeight: 550 }}>{e.event.replace(/_/g, ' ')}</strong>{e.detail ? `: ${e.detail}` : ''}</span></li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </>
  )
}
