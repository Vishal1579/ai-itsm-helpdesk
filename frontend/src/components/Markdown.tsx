import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

// Minimal, safe markdown for chat answers and KB articles: paragraphs, ordered/unordered lists,
// **bold**, `code`, ## headings and [KB0001] citations rendered as links. No raw HTML is ever injected.

function inline(text: string, keyBase: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[KB\d{4}\])/g)
  return parts.map((p, i) => {
    const key = `${keyBase}-${i}`
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={key}>{p.slice(2, -2)}</strong>
    if (p.startsWith('`') && p.endsWith('`')) return <code key={key}>{p.slice(1, -1)}</code>
    const kb = p.match(/^\[(KB\d{4})\]$/)
    if (kb) return <Link key={key} to={`/knowledge?article=${kb[1]}`} className="code">[{kb[1]}]</Link>
    return <Fragment key={key}>{p}</Fragment>
  })
}

export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, '').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }
    if (/^\s*\d+\.\s/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*\d+\.\s/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+\.\s/, ''))
      blocks.push(<ol key={i}>{items.map((it, j) => <li key={j}>{inline(it, `${i}-${j}`)}</li>)}</ol>)
      continue
    }
    if (/^\s*[-*]\s/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s/, ''))
      blocks.push(<ul key={i}>{items.map((it, j) => <li key={j}>{inline(it, `${i}-${j}`)}</li>)}</ul>)
      continue
    }
    const heading = line.match(/^#{1,3}\s+(.+)$/) ?? line.match(/^\*\*([^*]+)\*\*$/)
    if (heading) {
      blocks.push(line.startsWith('#') ? <h2 key={i}>{heading[1]}</h2> : <h4 key={i}>{heading[1]}</h4>)
      i++
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^\s*(\d+\.|[-*])\s/.test(lines[i]) && !/^#{1,3}\s/.test(lines[i])) para.push(lines[i++])
    blocks.push(<p key={i}>{inline(para.join(' '), String(i))}</p>)
  }
  return <div className="md">{blocks}</div>
}
