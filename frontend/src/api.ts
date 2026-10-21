// Typed client for the FastAPI backend (proxied by Vite at /api and /mock).

export type Intent = 'incident' | 'service_request' | 'knowledge_question' | 'automatable'

export interface Analysis {
  intent: Intent
  intent_confidence: number
  category: string
  subcategory: string
  category_confidence: number
  assignment_group: string
  impact: 'Individual' | 'Department' | 'Enterprise'
  urgency: 'Low' | 'Medium' | 'High'
  priority: 'P1' | 'P2' | 'P3' | 'P4'
  summary: string
  suggested_resolution: string
  kb_article: string | null
  playbook: string | null
  confidence: number
  threshold: number
  route: string
  software?: string
  intent_scores: Record<Intent, number>
  signals: string[]
}

export interface Source {
  article_id: string
  title: string
  section: string
  score: number
  snippet: string
}

export interface RagResult {
  grounded: boolean
  answer?: string
  sources: Source[]
  candidates?: Source[]
  confidence?: number
  retrieval_score?: number
  faithfulness?: number | null
  generation?: string
  model?: string
}

export interface AutomationStep {
  step: string
  status: 'success' | 'warning' | 'blocked' | 'failed'
  detail: string
  data: Record<string, unknown>
  at: string
  duration_ms: number
}

export interface Automation {
  run_id: string
  playbook: string
  playbook_name: string
  outcome: 'resolved' | 'escalated'
  message: string
  steps: AutomationStep[]
}

export interface SnRef {
  table: string
  number: string
  sys_id: string
  state: string
  state_label: string
  priority?: string
  assignment_group?: string
}

export interface SoftwareRequest {
  request_number: string
  ritm_number: string
  software: string
  version: string
  status: string
  progress: number
  approval_required: boolean
  job_id: string | null
  license?: string
  user_name?: string
  device?: string
  created_at?: string
  history?: { at: string; status: string; note: string }[]
}

export interface AuditEntry {
  audit_id: string
  timestamp: string
  actor: string
  action: string
  ticket_id: string | null
  status: string
  details: Record<string, unknown>
}

export interface Ticket {
  ticket_id: string
  type: 'incident' | 'service_request' | 'knowledge'
  channel: string
  user_id: string
  user_name: string
  description: string
  status: string
  resolved_by: 'ai' | 'human' | null
  escalated: boolean
  escalation_reason: string | null
  analysis: Analysis
  rag: RagResult | null
  automation: Automation | null
  diagnostics: { check: string; result: Record<string, unknown> } | null
  servicenow: SnRef | null
  software_request: SoftwareRequest | null
  timeline: { at: string; event: string; detail: string }[]
  created_at: string
  updated_at: string
  audit?: AuditEntry[]
}

export interface ChatResponse {
  session_id: string
  reply: string
  intent: Intent
  route: string
  confidence: number
  escalated: boolean
  actions: { type: string; label: string }[]
  ticket: Ticket
}

export interface Article {
  article_id: string
  title: string
  category: string
  subcategory: string
  tags: string[]
  owner: string
  summary: string
  content?: string
  chunk_count?: number
  views?: number
  updated_at?: string
}

export interface CatalogItem {
  sku: string
  name: string
  vendor: string
  version: string
  category: string
  license: string
  approval_required: boolean
  est_minutes: number
}

export interface User {
  user_id: string
  name: string
  department: string
  device: string
  role: string
}

export interface Health {
  status: string
  database: string
  llm: { provider: string; model: string; last_error: string | null }
  rag: { vector_db: string; embedding_model: string; chunks: number; articles: number }
  servicenow: { mode: string; instance: string | null }
  confidence_threshold: number
  rag_min_score: number
}

export type SnRecord = Record<string, string | undefined> & {
  number: string
  work_notes_history?: { at: string; note: string }[]
}

export interface DashboardTicket {
  ticket_id: string
  type: string
  status: string
  summary: string
  priority: string
  intent: Intent
  confidence: number
  created_at: string
  escalated: boolean
  resolved_by: string | null
  servicenow: string | null
}

export interface DashboardStats {
  totals: {
    total: number; open: number; ai_resolved: number; escalated: number; incidents: number; knowledge: number
    service_requests: number; software_requests: number; automation_runs: number; deflection_rate: number
    avg_confidence: number; knowledge_gaps: number
  }
  by_intent: Record<string, number>
  by_category: Record<string, number>
  by_priority: Record<string, number>
  by_status: Record<string, number>
  software_by_status: Record<string, number>
  automation: {
    outcomes: { resolved: number; escalated: number; blocked: number }
    by_playbook: Record<string, number>
    recent: { run_id: string; ticket_id: string; playbook: string; started_at: string; status: string; steps: number }[]
  }
  recent_tickets: DashboardTicket[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* body was not JSON */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

const post = <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) })

export const api = {
  health: () => request<Health>('/api/health'),
  users: () => request<User[]>('/api/users'),
  chat: (message: string, user_id: string, session_id?: string) => post<ChatResponse>('/api/chat', { message, user_id, session_id }),
  submitTicket: (description: string, user_id: string, request_type: string) =>
    post<ChatResponse>('/api/tickets', { description, user_id, request_type }),
  tickets: (params: Record<string, string> = {}) => request<Ticket[]>(`/api/tickets?${new URLSearchParams(params)}`),
  ticket: (id: string) => request<Ticket>(`/api/tickets/${id}`),
  escalate: (id: string) => post<{ ticket: Ticket; reply: string }>(`/api/tickets/${id}/escalate`),
  updateTicket: (id: string, body: { status?: string; work_note?: string }) =>
    request<Ticket>(`/api/tickets/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  snIncident: (number: string) => request<SnRecord>(`/api/servicenow/incident/${number}`),
  dashboard: () => request<DashboardStats>('/api/dashboard/stats'),
  articles: (params: Record<string, string> = {}) => request<Article[]>(`/api/kb/articles?${new URLSearchParams(params)}`),
  article: (id: string) => request<Article>(`/api/kb/articles/${id}`),
  categories: () => request<{ category: string; count: number }[]>('/api/kb/categories'),
  semanticSearch: (q: string) => request<{ query: string; min_score: number; results: (Source & { text: string })[] }>(`/api/kb/search?q=${encodeURIComponent(q)}&k=5`),
  ask: (question: string) => post<RagResult>('/api/kb/ask', { question }),
  gaps: () => request<{ gap_id: string; question: string; top_score: number; created_at: string; ticket_id: string }[]>('/api/kb/gaps'),
  publishArticle: (body: { title: string; category: string; subcategory: string; content: string; tags: string[] }) =>
    post<{ article: Article }>('/api/kb/articles', body),
  draftFromTicket: (id: string) => post<{ title: string; category: string; subcategory: string; content: string; generated_by: string }>(`/api/kb/drafts/from-ticket/${id}`),
  catalog: () => request<CatalogItem[]>('/api/catalog'),
  requests: () => request<SoftwareRequest[]>('/api/requests'),
  approve: (number: string, approved = true) => post<SoftwareRequest>(`/api/requests/${number}/approve`, { approved }),
  audit: () => request<AuditEntry[]>('/api/audit?limit=150'),
  resetDemo: () => post<{ status: string }>('/api/admin/reset-demo'),
}

export const INTENT_LABEL: Record<Intent, string> = {
  incident: 'Incident',
  service_request: 'Service request',
  knowledge_question: 'Knowledge question',
  automatable: 'Automatable issue',
}

export const STATUS_LABEL: Record<string, string> = {
  new: 'New',
  open: 'Open',
  in_progress: 'In progress',
  resolved: 'Resolved',
  closed: 'Closed',
  escalated: 'Escalated',
  provisioning: 'Provisioning',
  awaiting_approval: 'Awaiting approval',
  awaiting_user: 'Needs your decision',
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return new Date(iso).toLocaleDateString()
}
