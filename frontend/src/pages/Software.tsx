import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, timeAgo, type CatalogItem, type SoftwareRequest } from '../api'
import { useSession } from '../session'

export default function Software() {
  const { userId, toast } = useSession()
  const [catalog, setCatalog] = useState<CatalogItem[]>([])
  const [requests, setRequests] = useState<SoftwareRequest[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadRequests = useCallback(() => { api.requests().then(setRequests).catch((e) => setError(e.message)) }, [])
  useEffect(() => {
    api.catalog().then(setCatalog).catch((e) => setError(e.message))
    loadRequests()
  }, [loadRequests])

  const active = requests.some((r) => ['Provisioning', 'Approved'].includes(r.status))
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(loadRequests, 2000)
    return () => window.clearInterval(t)
  }, [active, loadRequests])

  const requestItem = async (item: CatalogItem) => {
    setBusy(item.sku)
    try {
      // Goes through the same AI intake as the chatbot: intent detection -> catalogue -> ServiceNow -> provisioning
      const res = await api.chat(`I need ${item.name} installed on my laptop`, userId)
      toast(`${res.ticket.software_request?.request_number ?? 'Request'} created for ${item.name}`)
      loadRequests()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const decide = async (r: SoftwareRequest, approved: boolean) => {
    setBusy(r.request_number)
    try {
      await api.approve(r.request_number, approved)
      toast(`${r.request_number} ${approved ? 'approved, provisioning started' : 'rejected'}`)
      loadRequests()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Software</h1>
          <p>Free tools install automatically. Licensed products wait for your line manager's approval first. Every request is tracked in ServiceNow.</p>
        </div>
      </div>
      {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="panel" style={{ marginBottom: 20 }}>
        <div className="panel-head"><h2>Requests</h2>{active && <span className="small faint">Updating live</span>}</div>
        {requests.length === 0 ? (
          <div className="empty"><p>No software requests yet. Pick something from the catalogue below, or ask the assistant.</p></div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Request</th><th>Software</th><th>For</th><th>Status</th><th>Progress</th><th /></tr></thead>
              <tbody>
                {requests.map((r) => (
                  <tr key={r.request_number}>
                    <td><div className="code">{r.request_number}</div><div className="small faint">{r.created_at ? timeAgo(r.created_at) : ''}</div></td>
                    <td><div style={{ fontWeight: 500 }}>{r.software}</div><div className="small faint">{r.version}, {r.license}</div></td>
                    <td className="small">{r.user_name}<div className="faint code">{r.device}</div></td>
                    <td><span className={`tag ${r.status === 'Completed' ? 'pine' : r.status === 'Rejected' ? 'p1' : r.status === 'Awaiting Approval' ? 'p2' : 'p3'}`}>{r.status}</span></td>
                    <td style={{ minWidth: 120 }}>
                      <div className="progress"><div style={{ width: `${r.progress}%` }} /></div>
                      <div className="small faint" style={{ marginTop: 4 }}>{r.history?.[r.history.length - 1]?.note}</div>
                    </td>
                    <td>
                      {r.status === 'Awaiting Approval' ? (
                        <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                          <button className="btn small primary" disabled={busy === r.request_number} onClick={() => decide(r, true)}>Approve as manager</button>
                          <button className="btn small" disabled={busy === r.request_number} onClick={() => decide(r, false)}>Reject</button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-head"><h2>Approved catalogue</h2><Link to="/knowledge?article=KB0007" className="small">How software requests work</Link></div>
        <div className="catalog">
          {catalog.map((c) => (
            <div key={c.sku} className="cat-item">
              <div className="spread"><strong>{c.name}</strong>{c.approval_required ? <span className="tag p2">Needs approval</span> : <span className="tag pine">Pre-approved</span>}</div>
              <div className="small muted">{c.vendor}, version {c.version}. About {c.est_minutes} min to install.</div>
              <div><button className="btn small" disabled={busy === c.sku} onClick={() => requestItem(c)}>{busy === c.sku ? 'Requesting…' : `Request ${c.name}`}</button></div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
