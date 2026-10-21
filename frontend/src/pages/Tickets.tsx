import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, INTENT_LABEL, timeAgo, type Ticket } from '../api'
import { Priority, ResolvedBy, StatusTag } from '../components/ui'

const FILTERS: { label: string; params: Record<string, string> }[] = [
  { label: 'All', params: {} },
  { label: 'Incidents', params: { type: 'incident' } },
  { label: 'Service requests', params: { type: 'service_request' } },
  { label: 'Questions', params: { type: 'knowledge' } },
  { label: 'Escalated', params: { status: 'escalated' } },
]

export default function Tickets() {
  const [filter, setFilter] = useState(0)
  const [tickets, setTickets] = useState<Ticket[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    setTickets(null)
    api.tickets(FILTERS[filter].params).then(setTickets).catch((e) => setError(e.message))
  }, [filter])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Tickets & AI analysis</h1>
          <p>Every request the assistant handled. Open one to see the full reasoning, the knowledge it used, automation steps, the ServiceNow record and the audit trail.</p>
        </div>
      </div>
      <div className="panel">
        <div className="tabs" role="tablist">
          {FILTERS.map((f, i) => (
            <button key={f.label} className="tab" role="tab" aria-selected={filter === i} onClick={() => setFilter(i)}>{f.label}</button>
          ))}
        </div>
        {error && <div className="error" style={{ margin: 16 }}>{error}</div>}
        {!tickets ? <p className="muted panel-pad">Loading…</p> : tickets.length === 0 ? (
          <div className="empty"><p>No tickets match this filter.</p></div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Request</th><th>Intent</th><th>Category</th><th>Priority</th><th>Confidence</th><th>Status</th><th>ServiceNow</th></tr></thead>
              <tbody>
                {tickets.map((t) => (
                  <tr key={t.ticket_id} className="clickable" onClick={() => navigate(`/tickets/${t.ticket_id}`)}>
                    <td style={{ maxWidth: 340 }}>
                      <div style={{ fontWeight: 500 }}>{t.analysis.summary}</div>
                      <div className="small faint">{t.user_name}, {timeAgo(t.created_at)}</div>
                    </td>
                    <td className="small">{INTENT_LABEL[t.analysis.intent]}</td>
                    <td className="small">{t.analysis.category} / {t.analysis.subcategory}</td>
                    <td>{t.type === 'incident' ? <Priority p={t.analysis.priority} /> : <span className="faint small">n/a</span>}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{Math.round(t.analysis.confidence * 100)}%</td>
                    <td><div className="row" style={{ gap: 6 }}><StatusTag status={t.status} /><ResolvedBy t={t} /></div></td>
                    <td className="code small">{t.servicenow?.number ?? <span className="faint">none</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
