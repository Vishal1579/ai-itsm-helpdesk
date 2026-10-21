import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, RotateCcw } from 'lucide-react'
import { api, INTENT_LABEL, timeAgo, type DashboardStats, type Intent } from '../api'
import { useSession } from '../session'
import { Priority, StatusTag } from '../components/ui'


export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useSession()
  const navigate = useNavigate()

  const load = useCallback(() => {
    api.dashboard().then((s) => { setStats(s); setError(null) }).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    load()
    const t = window.setInterval(load, 5000)
    return () => window.clearInterval(t)
  }, [load])

  const reset = async () => {
    if (!window.confirm('Clear all demo tickets, requests, chats and audit entries? Knowledge articles are kept.')) return
    await api.resetDemo()
    toast('Demo data cleared')
    load()
  }

  if (error) return <div className="error">Couldn't load the dashboard: {error}</div>
  if (!stats) return <p className="muted">Loading dashboard…</p>
  const t = stats.totals

  return (
    <>
      <div className="page-head">
        <div>
          <h1>ITSM dashboard</h1>
          <p>How requests are being handled right now: what the AI resolved, what went to people, and the state of automation and software requests.</p>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={load}><RefreshCw size={15} /> Refresh</button>
          <button className="btn" onClick={reset}><RotateCcw size={15} /> Reset demo data</button>
        </div>
      </div>

      <div className="kpis">
        <Kpi value={t.total} label="Total requests" note={`${t.incidents} incidents, ${t.knowledge} questions`} />
        <Kpi value={t.open} label="Open" note="New, in progress or waiting" />
        <Kpi value={t.ai_resolved} label="Resolved by AI" note={`${Math.round(t.deflection_rate * 100)}% of all requests`} accent />
        <Kpi value={t.escalated} label="Escalated to people" note="Low confidence or unsafe to automate" />
        <Kpi value={t.software_requests} label="Software requests" note={stats.software_by_status.Provisioning ? `${stats.software_by_status.Provisioning} provisioning now` : 'None provisioning'} />
        <Kpi value={t.automation_runs} label="Automation runs" note={`${stats.automation.outcomes.resolved} fixed, ${stats.automation.outcomes.blocked} blocked`} />
      </div>

      <div className="dash-grid">
        <div className="panel">
          <div className="panel-head"><h2>Requests by intent</h2></div>
          <div className="panel-pad">
            <Bars data={Object.fromEntries(Object.entries(stats.by_intent).map(([k, v]) => [INTENT_LABEL[k as Intent] ?? k, v]))} />
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><h2>By category</h2></div>
          <div className="panel-pad"><Bars data={stats.by_category} /></div>
        </div>
        <div className="panel">
          <div className="panel-head"><h2>Incidents by priority</h2></div>
          <div className="panel-pad"><Bars data={stats.by_priority} priority order={['P1', 'P2', 'P3', 'P4']} /></div>
        </div>

        <div className="panel span-2">
          <div className="panel-head"><h2>Latest requests</h2><span className="small faint">Updates every 5 seconds</span></div>
          {stats.recent_tickets.length === 0 ? (
            <div className="empty"><p>No requests yet. Ask the assistant something on the Get help page to see it appear here.</p></div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Request</th><th>Intent</th><th>Priority</th><th>Confidence</th><th>Status</th><th>ServiceNow</th></tr></thead>
                <tbody>
                  {stats.recent_tickets.map((r) => (
                    <tr key={r.ticket_id} className="clickable" onClick={() => navigate(`/tickets/${r.ticket_id}`)}>
                      <td><div style={{ fontWeight: 500 }}>{r.summary}</div><div className="small faint">{timeAgo(r.created_at)}</div></td>
                      <td className="small">{INTENT_LABEL[r.intent as Intent]}</td>
                      <td>{r.type === 'incident' ? <Priority p={r.priority} /> : <span className="faint">n/a</span>}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{Math.round(r.confidence * 100)}%</td>
                      <td><StatusTag status={r.status} /></td>
                      <td className="code small">{r.servicenow ?? <span className="faint">none</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-head"><h2>Automation</h2></div>
          <div className="panel-pad" style={{ display: 'grid', gap: 16 }}>
            <Bars data={{ 'Fixed and validated': stats.automation.outcomes.resolved, 'Escalated after trying': stats.automation.outcomes.escalated, 'Blocked by policy': stats.automation.outcomes.blocked }} />
            {stats.automation.recent.length > 0 && (
              <div style={{ display: 'grid', gap: 8 }}>
                {stats.automation.recent.slice(0, 5).map((r) => (
                  <button key={r.run_id} className="source" style={{ border: 0, textAlign: 'left', cursor: 'pointer' }} onClick={() => navigate(`/tickets/${r.ticket_id}`)}>
                    <div className="source-top"><span>{r.playbook.replace(/_/g, ' ')}</span><span className={`tag ${r.status === 'success' ? 'pine' : 'p2'}`}>{r.steps} steps</span></div>
                    <p className="code">{r.run_id}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head"><h2>Software requests</h2></div>
          <div className="panel-pad"><Bars data={stats.software_by_status} /></div>
        </div>
        <div className="panel">
          <div className="panel-head"><h2>AI quality</h2></div>
          <div className="panel-pad">
            <dl className="kv">
              <dt>Average confidence</dt><dd>{Math.round(t.avg_confidence * 100)}%</dd>
              <dt>Questions without an approved answer</dt><dd>{t.knowledge_gaps}</dd>
              <dt>Deflection rate</dt><dd>{Math.round(t.deflection_rate * 100)}%</dd>
            </dl>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><h2>Status</h2></div>
          <div className="panel-pad"><Bars data={stats.by_status} /></div>
        </div>
      </div>
    </>
  )
}

function Kpi({ value, label, note, accent }: { value: number; label: string; note: string; accent?: boolean }) {
  return (
    <div className="kpi">
      <div className="kpi-value" style={accent ? { color: 'var(--pine)' } : undefined}>{value}</div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-note">{note}</div>
    </div>
  )
}

function Bars({ data, priority, order }: { data: Record<string, number>; priority?: boolean; order?: string[] }) {
  const entries = order ? order.map((k) => [k, data[k] ?? 0] as [string, number]) : Object.entries(data)
  const max = Math.max(1, ...entries.map(([, v]) => v))
  if (!entries.length || entries.every(([, v]) => v === 0)) return <p className="small faint">Nothing to show yet.</p>
  return (
    <div className="bars">
      {entries.map(([k, v]) => (
        <div className="bar-row" key={k}>
          <span className="small" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={k}>{k.replace(/_/g, ' ')}</span>
          <div className="bar-track"><div className={`bar-fill${priority ? ` ${k}` : ''}`} style={{ width: `${(v / max) * 100}%` }} /></div>
          <span className="bar-num small">{v}</span>
        </div>
      ))}
    </div>
  )
}
