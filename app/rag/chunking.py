"""Knowledge document parsing and heading-aware chunking."""
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class KnowledgeDoc:
    article_id: str
    title: str
    category: str
    subcategory: str
    tags: list[str]
    owner: str
    body: str
    source_file: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def checksum(self) -> str:
        return hashlib.sha256(f"{self.title}\n{self.body}".encode()).hexdigest()[:16]


@dataclass
class Chunk:
    chunk_id: str
    article_id: str
    title: str
    section: str
    text: str
    category: str
    subcategory: str

    @property
    def embedding_text(self) -> str:
        # Title + section context makes short chunks far easier to retrieve
        return f"{self.title} - {self.section}\n{self.text}"


def parse_markdown(text: str, source_file: str = "") -> KnowledgeDoc:
    meta: dict[str, str] = {}
    body = text
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    title = meta.get("title") or (re.search(r"^# (.+)$", body, re.M) or [None, Path(source_file).stem])[1]
    return KnowledgeDoc(
        article_id=meta.get("id") or Path(source_file).stem,
        title=title,
        category=meta.get("category", "General"),
        subcategory=meta.get("subcategory", "General"),
        tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        owner=meta.get("owner", "Service Desk"),
        body=body.strip(),
        source_file=source_file,
        meta=meta,
    )


def load_directory(path: Path) -> list[KnowledgeDoc]:
    return [parse_markdown(p.read_text(encoding="utf-8"), p.name) for p in sorted(path.glob("*.md"))]


def chunk_document(doc: KnowledgeDoc, size: int = 120, overlap: int = 30) -> list[Chunk]:
    """Split on markdown headings first, then window long sections by words with overlap."""
    sections: list[tuple[str, str]] = []
    current, buf = "Overview", []
    for line in doc.body.splitlines():
        h = re.match(r"^#{1,3}\s+(.+)$", line)
        if h:
            if "".join(buf).strip():
                sections.append((current, "\n".join(buf).strip()))
            current = h.group(1).strip() if not line.startswith("# ") else "Overview"
            buf = []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append((current, "\n".join(buf).strip()))

    chunks: list[Chunk] = []
    for section, text in sections:
        for window in _pack_lines(text, size, overlap):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.article_id}-{len(chunks):02d}",
                    article_id=doc.article_id,
                    title=doc.title,
                    section=section,
                    text=window,
                    category=doc.category,
                    subcategory=doc.subcategory,
                )
            )
    return chunks


def _pack_lines(text: str, size: int, overlap: int) -> list[str]:
    """Pack whole lines (list items / sentences) into windows of ~`size` words, never cutting a step
    in half; consecutive windows share trailing lines worth ~`overlap` words."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    windows, cur, count = [], [], 0
    for ln in lines:
        n = len(ln.split())
        if cur and count + n > size:
            windows.append("\n".join(cur))
            keep, kept = [], 0
            for prev in reversed(cur):
                if kept + len(prev.split()) > overlap:
                    break
                keep.insert(0, prev)
                kept += len(prev.split())
            cur, count = keep, kept
        cur.append(ln)
        count += n
    if cur:
        windows.append("\n".join(cur))
    return windows
