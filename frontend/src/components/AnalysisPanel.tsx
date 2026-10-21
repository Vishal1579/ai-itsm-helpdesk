import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import type { Ticket } from '../api'
import { INTENT_LABEL } from '../api'
import { ConfidenceMeter, DecisionTrace, Notice, Priority, ResolvedBy, Sources, StatusTag } from './ui'

const INTENTS = ['incident', 'automatable', 'service_request', 'knowledge_question'] as const

export function AnalysisPanel({ ticket, animate = false, showLink = true }: { ticket: Ticket; animate?: boolean; showLink?: boolean }) {
  const a = ticket.analysis
  const rag = ticket.rag
  const sn = ticket.servicenow
  const sr = ticket.software_request
  return (
    <>
      <section>
        <div className="analysis-head">
          <div>
            <div className="faint small">Routed to</div>
            <div className="route">{a.route}</div>
          </div>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <StatusTag status={ticket.status} />
            <ResolvedBy t={ticket} />
          </div>
        </div>
        <ConfidenceMeter value={a.confidence} threshold={a.threshold ?? 0.6} />
        {ticket.escalation_reason && <Notice tone="warn">{ticket.escalation_reason}</Notice>}
      </section>

      <section>
        <h3>Triage</h3>
        <div className="facts">
          <div className="fact"><span>Intent</span><strong>{INTENT_LABEL[a.intent]}</strong></div>
          <div className="fact"><span>Category / sub-category</span><strong>{a.category} / {a.subcategory}</strong></div>
          <div className="fact"><span>Priority</span><Priority p={a.priority} /></div>
          <div className="fact"><span>Impact / urgency</span><strong>{a.impact} / {a.urgency}</strong></div>
          <div className="fact"><span>Assignment group</span><strong>{a.assignment_group}</strong></div>
          <div className="fact"><span>Summary</span><strong>{a.summary}</strong></div>
          <div className="fact" style={{ gridColumn: '1 / -1' }}><span>Suggested resolution</span><strong>{a.suggested_resolution}</strong></div>
        </div>
        <details>
          <summary className="small muted" style={{ cursor: 'pointer' }}>Why the AI decided this</summary>
          <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
            <ul className="signals">{a.signals.map((s) => <li key={s}>{s}</li>)}</ul>
            <div className="bars">
              {INTENTS.map((i) => (
                <div className="bar-row" key={i}>
                  <span className="small muted">{INTENT_LABEL[i]}</span>
                  <div className="bar-track"><div className="bar-fill" style={{ width: `${(a.intent_scores?.[i] ?? 0) * 100}%`, opacity: i === a.intent ? 1 : 0.35 }} /></div>
                  <span className="bar-num small">{Math.round((a.intent_scores?.[i] ?? 0) * 100)}</span>
                </div>
              ))}
            </div>
            <div className="small faint">Intent confidence {Math.round(a.intent_confidence * 100)}%, category {Math.round(a.category_confidence * 100)}%</div>
          </div>
        </details>
      </section>

      {ticket.automation && (
        <section>
          <div className="spread">
            <h3>Self-heal: {ticket.automation.playbook_name}</h3>
            <span className="code faint">{ticket.automation.run_id}</span>
          </div>
          <DecisionTrace steps={ticket.automation.steps} animate={animate} />
        </section>
      )}

      {ticket.diagnostics && (
        <section>
          <h3>{ticket.diagnostics.check}</h3>
          <dl className="kv small">
            {Object.entries(ticket.diagnostics.result).filter(([k]) => k !== 'user_id').map(([k, v]) => (
              <div key={k} style={{ display: 'contents' }}><dt>{k.replace(/_/g, ' ')}</dt><dd>{String(v)}</dd></div>
            ))}
          </dl>
        </section>
      )}

      {rag && (
        <section>
          <div className="spread">
            <h3>Knowledge used</h3>
            {rag.grounded ? <span className="tag pine">Grounded in approved KB</span> : <span className="tag p2">Not in approved KB</span>}
          </div>
          {rag.sources.length > 0 ? <Sources sources={rag.sources} /> : (
            <p className="small muted">
              No article scored above the relevance cut-off
              {typeof rag.retrieval_score === 'number' ? ` (best match ${rag.retrieval_score.toFixed(2)})` : ''}, so no answer was generated.
            </p>
          )}
          {rag.generation && rag.grounded && (
            <div className="small faint">
              Answer by {rag.generation === 'llm' ? rag.model : 'extractive summary'}
              {typeof rag.faithfulness === 'number' ? `, faithfulness ${rag.faithfulness.toFixed(2)}` : ''}
            </div>
          )}
        </section>
      )}

      {sr && (
        <section>
          <div className="spread">
            <h3>{sr.software}</h3>
            <span className="tag p3">{sr.status}</span>
          </div>
          <div className="progress" aria-label="Provisioning progress"><div style={{ width: `${sr.progress ?? 0}%` }} /></div>
          <dl className="kv small">
            <dt>Request</dt><dd className="code">{sr.request_number}</dd>
            <dt>Item</dt><dd className="code">{sr.ritm_number}</dd>
            <dt>Version</dt><dd>{sr.version}</dd>
            {sr.job_id && <><dt>Provisioning job</dt><dd className="code">{sr.job_id}</dd></>}
          </dl>
        </section>
      )}

      {sn && (
        <section>
          <div className="sn-card">
            <div>
              <div className="faint small">ServiceNow {sn.table === 'incident' ? 'incident' : 'request'}</div>
              <div className="sn-number">{sn.number}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="small">{sn.state_label}</div>
              {showLink && (
                <Link to={`/tickets/${ticket.ticket_id}`} className="small row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                  Full analysis <ExternalLink size={13} />
                </Link>
              )}
            </div>
          </div>
        </section>
      )}
    </>
  )
}
