import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowLeft, Search } from 'lucide-react'
import { api, timeAgo, type Article, type Health, type RagResult, type Source } from '../api'
import { useSession } from '../session'
import { Markdown } from '../components/Markdown'
import { ScoreBar } from '../components/ui'

type Hit = Source & { text: string }

export default function Knowledge() {
  const [params, setParams] = useSearchParams()
  const articleId = params.get('article')
  const [articles, setArticles] = useState<Article[]>([])
  const [categories, setCategories] = useState<{ category: string; count: number }[]>([])
  const [category, setCategory] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [showPublish, setShowPublish] = useState(params.get('draft') === '1')

  const refresh = () => {
    api.articles().then(setArticles).catch(() => {})
    api.categories().then(setCategories).catch(() => {})
    api.health().then(setHealth).catch(() => {})
  }
  useEffect(refresh, [])

  const visible = useMemo(() => {
    const q = filter.toLowerCase()
    return articles.filter((a) => (!category || a.category === category) &&
      (!q || a.title.toLowerCase().includes(q) || a.tags.some((t) => t.includes(q)) || a.summary.toLowerCase().includes(q)))
  }, [articles, category, filter])

  if (articleId) return <ArticleView id={articleId} onBack={() => setParams({})} />

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Knowledge base</h1>
          <p>Approved IT articles. The assistant answers only from these, and says so when they don't cover a question.</p>
        </div>
        <button className="btn" onClick={() => setShowPublish((s) => !s)}>{showPublish ? 'Close editor' : 'Publish an article'}</button>
      </div>

      {showPublish && <PublishForm onPublished={(id) => { setShowPublish(false); refresh(); setParams({ article: id }) }} />}

      <AskPanel minScore={health?.rag_min_score ?? 0.45} />

      {health && (
        <div className="panel panel-pad small" style={{ margin: '20px 0', display: 'grid', gap: 10 }}>
          <h3>How answers are produced</h3>
          <ol className="row muted" style={{ margin: 0, paddingLeft: 18, gap: '6px 26px' }}>
            <li>{health.rag.articles} articles split into {health.rag.chunks} heading-aware chunks</li>
            <li>Embedded with {health.rag.embedding_model.split('/')[1]}</li>
            <li>Stored in {health.rag.vector_db}</li>
            <li>Top matches above {health.rag_min_score} similarity retrieved</li>
            <li>{health.llm.model.split('/').pop()} writes an answer from those passages only</li>
            <li>Answer checked against its sources before it's shown</li>
          </ol>
        </div>
      )}

      <div className="kb-grid">
        <div className="panel">
          <div className="cat-list" role="group" aria-label="Categories">
            <button className="cat-btn" aria-pressed={!category} onClick={() => setCategory(null)}><span>All articles</span><span>{articles.length}</span></button>
            {categories.map((c) => (
              <button key={c.category} className="cat-btn" aria-pressed={category === c.category} onClick={() => setCategory(c.category)}>
                <span>{c.category}</span><span>{c.count}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="stack">
          <div className="panel">
            <div className="panel-head">
              <h2>{category ?? 'All articles'}</h2>
              <input className="input" style={{ maxWidth: 240 }} placeholder="Filter by title or tag" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter articles" />
            </div>
            {visible.length === 0 ? <div className="empty"><p>No articles match “{filter}”.</p></div> : visible.map((a) => (
              <button key={a.article_id} className="article-row" onClick={() => setParams({ article: a.article_id })}>
                <span className="code faint">{a.article_id}</span>
                <span>
                  <span style={{ fontWeight: 600, display: 'block' }}>{a.title}</span>
                  <span className="small muted">{a.summary}</span>
                </span>
                <span className="tag">{a.subcategory}</span>
              </button>
            ))}
          </div>
          <Gaps />
        </div>
      </div>
    </>
  )
}

function AskPanel({ minScore }: { minScore: number }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<RagResult | null>(null)
  const [hits, setHits] = useState<Hit[]>([])
  const [error, setError] = useState<string | null>(null)

  const ask = async (e: React.FormEvent) => {
    e.preventDefault()
    if (q.trim().length < 2) return
    setBusy(true); setError(null)
    try {
      const [r, s] = await Promise.all([api.ask(q), api.semanticSearch(q)])
      setResult(r); setHits(s.results)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <form className="panel-pad row" onSubmit={ask} style={{ alignItems: 'stretch' }}>
        <input className="input" style={{ flex: 1, minWidth: 220 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question, for example: how do I fix a stuck print job?" aria-label="Ask the knowledge base" />
        <button className="btn primary" disabled={busy || q.trim().length < 2}><Search size={15} /> {busy ? 'Searching…' : 'Ask'}</button>
      </form>
      {error && <div className="error" style={{ margin: '0 20px 16px' }}>{error}</div>}
      {result && (
        <div className="detail-grid" style={{ borderTop: '1px solid var(--rule)', padding: 20, gap: 24 }}>
          <div style={{ display: 'grid', gap: 10, alignContent: 'start' }}>
            <div className="row">
              {result.grounded ? <span className="tag pine">Grounded in approved KB</span> : <span className="tag p2">Not covered by approved KB</span>}
              <span className="small faint">Confidence {Math.round((result.confidence ?? 0) * 100)}%{result.generation === 'llm' ? `, written by ${result.model?.split('/').pop()}` : ''}</span>
            </div>
            <Markdown text={result.answer ?? ''} />
          </div>
          <div style={{ display: 'grid', gap: 8, alignContent: 'start' }}>
            <h3>Retrieved passages</h3>
            <p className="small faint">Cosine similarity. Passages below {minScore} are never used.</p>
            {hits.map((h) => (
              <div key={`${h.article_id}-${h.section}`} className="source" style={{ opacity: h.score < minScore ? 0.55 : 1 }}>
                <div className="source-top"><span><span className="code">{h.article_id}</span> {h.section}</span><ScoreBar score={h.score} threshold={minScore} /></div>
                <p>{h.text.slice(0, 160)}{h.text.length > 160 ? '…' : ''}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ArticleView({ id, onBack }: { id: string; onBack: () => void }) {
  const [a, setA] = useState<Article | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.article(id).then(setA).catch((e) => setError(e.message)) }, [id])
  if (error) return <div className="error">Article {id} couldn't be loaded: {error}</div>
  if (!a) return <p className="muted">Loading article…</p>
  return (
    <>
      <button className="btn ghost" onClick={onBack} style={{ marginBottom: 12 }}><ArrowLeft size={15} /> Knowledge base</button>
      <div className="panel">
        <div className="panel-head">
          <div className="row"><span className="code">{a.article_id}</span><span className="tag">{a.category} / {a.subcategory}</span></div>
          <span className="small faint">Owner: {a.owner}{a.chunk_count ? `, ${a.chunk_count} indexed chunks` : ''}</span>
        </div>
        <article className="article-body"><Markdown text={a.content ?? ''} /></article>
      </div>
    </>
  )
}

function Gaps() {
  const [gaps, setGaps] = useState<Awaited<ReturnType<typeof api.gaps>>>([])
  useEffect(() => { api.gaps().then(setGaps).catch(() => {}) }, [])
  return (
    <div className="panel">
      <div className="panel-head"><h2>Unanswered questions</h2><span className="small faint">Candidates for new articles</span></div>
      {gaps.length === 0 ? <div className="empty small"><p>Every question so far was covered by an approved article.</p></div> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Question</th><th>Best match</th><th>Asked</th></tr></thead>
            <tbody>{gaps.map((g) => (
              <tr key={g.gap_id}><td>{g.question}</td><td><ScoreBar score={g.top_score} /></td><td className="small faint">{timeAgo(g.created_at)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PublishForm({ onPublished }: { onPublished: (id: string) => void }) {
  const { toast } = useSession()
  const draft = useMemo(() => {
    try { return JSON.parse(sessionStorage.getItem('itsm.kbDraft') ?? 'null') } catch { return null }
  }, [])
  const [form, setForm] = useState({
    title: draft?.title ?? '', category: draft?.category ?? 'Hardware', subcategory: draft?.subcategory ?? '', content: draft?.content ?? '', tags: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const res = await api.publishArticle({ ...form, tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean) })
      try { sessionStorage.removeItem('itsm.kbDraft') } catch { /* ignore */ }
      toast(`${res.article.article_id} published and indexed`)
      onPublished(res.article.article_id)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel panel-pad" onSubmit={submit} style={{ display: 'grid', gap: 14, marginBottom: 20 }}>
      <div className="spread">
        <h2>{draft ? 'Review the AI draft' : 'Publish an article'}</h2>
        {draft && <span className="small faint">Drafted by {draft.generated_by} from ticket {draft.source_ticket}</span>}
      </div>
      <p className="small muted">Publishing chunks, embeds and indexes the article straight away, so the assistant can use it in the next answer.</p>
      <div className="facts">
        <label className="field"><span>Title</span><input className="input" value={form.title} onChange={set('title')} required minLength={5} /></label>
        <label className="field"><span>Category</span>
          <select className="select" value={form.category} onChange={set('category')}>
            {['Network', 'Access', 'Email', 'Hardware', 'Software', 'Collaboration', 'General'].map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className="field"><span>Sub-category</span><input className="input" value={form.subcategory} onChange={set('subcategory')} required /></label>
        <label className="field"><span>Tags (comma separated)</span><input className="input" value={form.tags} onChange={set('tags')} /></label>
      </div>
      <label className="field"><span>Content (markdown)</span><textarea className="textarea" rows={10} value={form.content} onChange={set('content')} required minLength={40} /></label>
      {error && <div className="error">{error}</div>}
      <div><button className="btn primary" disabled={busy}>{busy ? 'Publishing…' : 'Publish article'}</button></div>
    </form>
  )
}
