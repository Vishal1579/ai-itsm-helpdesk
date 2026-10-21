import { Link } from 'react-router-dom'
import { Check, X, AlertTriangle } from 'lucide-react'
import type { AutomationStep, Source, Ticket } from '../api'
import { STATUS_LABEL } from '../api'

export function ConfidenceMeter({ value, threshold, label = 'AI confidence' }: { value: number; threshold: number; label?: string }) {
  const pct = Math.round(value * 100)
  const low = value < threshold
  return (
    <div className="meter">
      <div className="meter-top">
        <span className="muted">{label}</span>
        <span className="meter-value" style={{ color: low ? 'var(--p2)' : 'var(--pine)' }}>{pct}%</span>
      </div>
      <div className="meter-track" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={label}>
        <div className={`meter-fill${low ? ' low' : ''}`} style={{ width: `${pct}%` }} />
        <div className="meter-threshold" style={{ left: `calc(${threshold * 100}% - 1px)` }} title={`Escalation threshold ${Math.round(threshold * 100)}%`} />
      </div>
      <div className="meter-legend">
        {low
          ? `Below the ${Math.round(threshold * 100)}% threshold, so a person reviews this`
          : `Above the ${Math.round(threshold * 100)}% threshold, so the AI can act on its own`}
      </div>
    </div>
  )
}

export function Priority({ p }: { p: string }) {
  return <span className={`prio ${p}`}>{p}</span>
}

const STATUS_TONE: Record<string, string> = {
  resolved: 'pine', closed: 'pine', escalated: 'p2', awaiting_user: 'p2', awaiting_approval: 'p3', provisioning: 'p3', open: 'p3', new: 'p3',
}

export function StatusTag({ status }: { status: string }) {
  return <span className={`tag ${STATUS_TONE[status] ?? ''}`}>{STATUS_LABEL[status] ?? status}</span>
}

export function ResolvedBy({ t }: { t: Pick<Ticket, 'resolved_by' | 'escalated'> }) {
  if (t.resolved_by === 'ai') return <span className="tag pine">Resolved by AI</span>
  if (t.resolved_by === 'human') return <span className="tag">Resolved by analyst</span>
  if (t.escalated) return <span className="tag p2">With a person</span>
  return null
}

const STEP_ICON = { success: <Check size={14} strokeWidth={3} />, warning: '!', blocked: <X size={14} strokeWidth={3} />, failed: <X size={14} strokeWidth={3} /> }

export function DecisionTrace({ steps, animate = false }: { steps: AutomationStep[]; animate?: boolean }) {
  return (
    <ol className={`trace${animate ? ' animate' : ''}`}>
      {steps.map((s, i) => (
        <li key={`${s.step}-${i}`} className={s.status}>
          <span className="trace-node" aria-hidden>{STEP_ICON[s.status] ?? i + 1}</span>
          <div>
            <div className="trace-title">
              {s.step}
              {s.duration_ms > 0 && <span className="faint">{s.duration_ms} ms</span>}
              {s.status !== 'success' && <span className={`tag ${s.status === 'warning' ? 'p2' : 'p1'}`}>{s.status}</span>}
            </div>
            <div className="trace-detail">{s.detail}</div>
          </div>
        </li>
      ))}
    </ol>
  )
}

export function Sources({ sources, threshold }: { sources: Source[]; threshold?: number }) {
  if (!sources.length) return null
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {sources.map((s) => (
        <Link key={`${s.article_id}-${s.section}`} to={`/knowledge?article=${s.article_id}`} className="source" style={{ textDecoration: 'none' }}>
          <div className="source-top">
            <span><span className="code">{s.article_id}</span> {s.title}</span>
            <ScoreBar score={s.score} threshold={threshold} />
          </div>
          <p>{s.section}</p>
        </Link>
      ))}
    </div>
  )
}

export function ScoreBar({ score, threshold = 0.45 }: { score: number; threshold?: number }) {
  return (
    <span className="row small" style={{ gap: 6 }} title={`Cosine similarity ${score.toFixed(3)}`}>
      <span className="score-bar"><i className={score < threshold ? 'below' : ''} style={{ width: `${Math.max(4, Math.min(100, score * 100))}%` }} /></span>
      <span className="faint" style={{ fontVariantNumeric: 'tabular-nums' }}>{score.toFixed(2)}</span>
    </span>
  )
}

export function Notice({ tone, children }: { tone: 'warn' | 'error'; children: React.ReactNode }) {
  return (
    <div className={tone === 'error' ? 'error' : 'sunk'} style={{ padding: '10px 14px', display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: '0.9rem' }}>
      <AlertTriangle size={16} style={{ flex: 'none', marginTop: 2, color: 'var(--p2)' }} />
      <div>{children}</div>
    </div>
  )
}
