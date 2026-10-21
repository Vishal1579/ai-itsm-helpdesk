"""RAG pipeline: Document -> Chunking -> Embedding -> FAISS -> Semantic Search -> LLM -> Grounded Response."""
import asyncio
import hashlib
import logging
import re

import numpy as np

from app.ai.embeddings import get_embedder
from app.ai.llm import get_llm
from app.config import get_settings
from app.db import KB_CHUNKS, KNOWLEDGE, clean, get_db, utcnow
from app.rag.chunking import Chunk, KnowledgeDoc, chunk_document, load_directory
from app.rag.vector_store import FaissVectorStore

log = logging.getLogger(__name__)

CHUNKER_VERSION = "lines-v2"

NO_ANSWER = (
    "I could not find this in the approved IT Knowledge Base, so I won't guess. "
    "I can raise a ticket so a Service Desk analyst can help you."
)

SYSTEM_PROMPT = """You are an enterprise IT helpdesk assistant.
Answer the employee's question using ONLY the knowledge base context provided.
Rules:
- Do not use outside knowledge and do not invent steps, URLs, tools or policies.
- Give short numbered steps when the context contains steps.
- Cite the article ids you used in square brackets, e.g. [KB0004].
- If the context does not answer the question, reply exactly: INSUFFICIENT_CONTEXT"""


class RAGService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedder = get_embedder()
        self.store = FaissVectorStore(self.settings.vector_store_dir, self.embedder.dim)
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------- ingestion
    async def sync_from_disk(self) -> int:
        """Upsert the markdown knowledge documents into MongoDB (knowledge metadata collection)."""
        docs = load_directory(self.settings.kb_dir)
        db = get_db()
        for doc in docs:
            existing = await db[KNOWLEDGE].find_one({"article_id": doc.article_id})
            if existing and existing.get("checksum") == doc.checksum:
                continue
            await db[KNOWLEDGE].update_one(
                {"article_id": doc.article_id},
                {
                    "$set": {**_doc_record(doc), "updated_at": utcnow()},
                    "$setOnInsert": {"created_at": utcnow(), "views": 0, "helpful": 0},
                },
                upsert=True,
            )
        return len(docs)

    async def build_index(self, force: bool = False) -> dict:
        async with self._lock:
            articles = await get_db()[KNOWLEDGE].find({"status": "published"}).to_list(None)
            docs = [_record_doc(a) for a in articles]
            fingerprint = hashlib.sha256(
                (f"{self.embedder.model_name}|{CHUNKER_VERSION}|{self.settings.chunk_size_words}|{self.settings.chunk_overlap_words}|"
                 + "".join(sorted(d.checksum for d in docs))).encode()
            ).hexdigest()[:16]
            if not force and self.store.fingerprint is None:
                self.store.load()
            # Reuse the on-disk index only if this database already holds its chunks (a new DB needs them written)
            if not force and self.store.fingerprint == fingerprint and self.store.size and await get_db()[KB_CHUNKS].count_documents({}):
                return self.stats()

            chunks: list[Chunk] = []
            for d in docs:
                chunks.extend(chunk_document(d, self.settings.chunk_size_words, self.settings.chunk_overlap_words))
            vectors = (
                await asyncio.to_thread(self.embedder.encode, [c.embedding_text for c in chunks])
                if chunks
                else np.zeros((0, self.embedder.dim), dtype="float32")
            )
            self.store.rebuild(chunks, vectors, fingerprint)

            db = get_db()
            await db[KB_CHUNKS].delete_many({})
            if chunks:
                await db[KB_CHUNKS].insert_many(
                    [{**c.__dict__, "embedding_model": self.embedder.model_name, "indexed_at": utcnow()} for c in chunks]
                )
            for d in docs:
                await db[KNOWLEDGE].update_one(
                    {"article_id": d.article_id},
                    {"$set": {"chunk_count": sum(c.article_id == d.article_id for c in chunks), "indexed_at": utcnow()}},
                )
            log.info("Indexed %d articles into %d chunks", len(docs), len(chunks))
            return self.stats()

    def section_text(self, article_id: str, section: str) -> str:
        """Re-assemble a full section from its (overlapping) chunks."""
        lines: list[str] = []
        for c in self.store.chunks:
            if c.article_id == article_id and c.section == section:
                lines += [ln for ln in c.text.splitlines() if ln not in lines]
        return "\n".join(lines)

    def stats(self) -> dict:
        return {
            "vector_db": "FAISS (IndexFlatIP, cosine)",
            "embedding_model": self.embedder.model_name,
            "chunks": self.store.size,
            "articles": len({c.article_id for c in self.store.chunks}),
            "fingerprint": self.store.fingerprint,
        }

    # ---------------------------------------------------------------- retrieval
    async def search(self, query: str, k: int | None = None) -> list[dict]:
        k = k or self.settings.rag_top_k
        qvec = (await asyncio.to_thread(self.embedder.encode, [query]))[0]
        hits = self.store.search(qvec, k * 3)
        # keep the best chunk per (article, section) so sources are diverse
        seen, results = set(), []
        for chunk, score in hits:
            key = (chunk.article_id, chunk.section)
            if key in seen:
                continue
            seen.add(key)
            results.append({**chunk.__dict__, "score": round(score, 4)})
            if len(results) >= k:
                break
        return results

    # ---------------------------------------------------------------- generation
    async def answer(self, question: str) -> dict:
        min_score = self.settings.rag_min_score
        hits = await self.search(question, k=6)
        relevant = _rerank(question, [h for h in hits if h["score"] >= min_score])[: self.settings.rag_top_k]
        top = hits[0]["score"] if hits else 0.0
        retrieval_conf = _retrieval_confidence(top, min_score)
        sources = [_source(h) for h in relevant]

        if not relevant:
            return {
                "grounded": False,
                "answer": NO_ANSWER,
                "sources": [],
                "candidates": [_source(h) for h in hits[:2]],
                "confidence": round(retrieval_conf, 3),
                "retrieval_score": top,
                "generation": "none",
                "model": get_llm().model_name,
            }

        # Context: top chunks, preferring the best article first
        context_hits = relevant[:3]
        context = "\n\n".join(f"[{h['article_id']}] {h['title']} - {h['section']}\n{h['text']}" for h in context_hits)
        llm = get_llm()
        generated = await llm.generate(SYSTEM_PROMPT, f"Knowledge base context:\n{context}\n\nQuestion: {question}")
        generation = "llm"
        faithfulness = None
        if generated and "INSUFFICIENT_CONTEXT" in generated:
            if retrieval_conf < 0.75:
                return {
                    "grounded": False,
                    "answer": NO_ANSWER,
                    "sources": [],
                    "candidates": sources[:2],
                    "confidence": round(retrieval_conf * 0.6, 3),
                    "retrieval_score": top,
                    "generation": "llm-declined",
                    "model": llm.model_name,
                }
            generated = None
        if generated:
            # Faithfulness guard: the answer must stay semantically close to the retrieved context
            vecs = await asyncio.to_thread(self.embedder.encode, [generated, context])
            faithfulness = float(np.dot(vecs[0], vecs[1]))
            if faithfulness < 0.45 or len(generated) < 20:
                log.info("LLM answer rejected by faithfulness guard (%.2f)", faithfulness)
                generated = None
        if not generated:
            generated, generation = _extractive_answer(context_hits, self.section_text), "extractive"
        answer = _ensure_citations(generated, context_hits)
        conf = retrieval_conf if faithfulness is None else 0.7 * retrieval_conf + 0.3 * max(0.0, faithfulness)
        return {
            "grounded": True,
            "answer": answer,
            "sources": sources,
            "confidence": round(min(conf, 0.99), 3),
            "retrieval_score": top,
            "faithfulness": round(faithfulness, 3) if faithfulness is not None else None,
            "generation": generation,
            "model": llm.model_name if generation == "llm" else "extractive",
        }

    # ---------------------------------------------------------------- KM automation
    async def publish_article(self, doc: KnowledgeDoc, author: str = "kb-automation") -> dict:
        db = get_db()
        await db[KNOWLEDGE].update_one(
            {"article_id": doc.article_id},
            {"$set": {**_doc_record(doc), "author": author, "updated_at": utcnow()}, "$setOnInsert": {"created_at": utcnow(), "views": 0, "helpful": 0}},
            upsert=True,
        )
        stats = await self.build_index()
        return {"article": clean(await db[KNOWLEDGE].find_one({"article_id": doc.article_id})), "index": stats}


def _doc_record(doc: KnowledgeDoc) -> dict:
    return {
        "article_id": doc.article_id,
        "title": doc.title,
        "category": doc.category,
        "subcategory": doc.subcategory,
        "tags": doc.tags,
        "owner": doc.owner,
        "content": doc.body,
        "source_file": doc.source_file,
        "checksum": doc.checksum,
        "status": "published",
        "summary": _summary(doc.body),
    }


def _record_doc(rec: dict) -> KnowledgeDoc:
    return KnowledgeDoc(
        article_id=rec["article_id"], title=rec["title"], category=rec.get("category", "General"),
        subcategory=rec.get("subcategory", "General"), tags=rec.get("tags", []), owner=rec.get("owner", ""),
        body=rec["content"], source_file=rec.get("source_file", ""),
    )


def _summary(body: str) -> str:
    for para in body.split("\n\n"):
        p = para.strip()
        if p and not p.startswith("#"):
            return p[:240]
    return ""


def _source(h: dict) -> dict:
    return {
        "article_id": h["article_id"],
        "title": h["title"],
        "section": h["section"],
        "score": h["score"],
        "snippet": h["text"][:220] + ("..." if len(h["text"]) > 220 else ""),
    }


STOPWORDS = {"what", "when", "where", "which", "with", "your", "have", "does", "should", "there", "this", "that", "from", "about", "how", "can"}


def _rerank(question: str, hits: list[dict]) -> list[dict]:
    """Light re-ranking on top of vector similarity: prefer procedural chunks and lexical overlap
    so 'how do I...' questions get the steps section instead of 'When to escalate'."""
    terms = {w for w in re.findall(r"[a-z]{4,}", question.lower()) if w not in STOPWORDS}

    def boost(h: dict) -> float:
        text = h["text"].lower()
        b = 0.05 if re.search(r"^\s*\d+\.", h["text"], re.M) else 0.0
        b += 0.06 * (sum(1 for t in terms if t[:6] in text or t[:6] in h["section"].lower()) / max(1, len(terms)))
        if h["section"].lower() in ("when to escalate", "symptoms"):
            b -= 0.05
        return h["score"] + b

    return sorted(hits, key=boost, reverse=True)


def _retrieval_confidence(top: float, min_score: float) -> float:
    """Map raw cosine similarity onto a 0-1 confidence where `min_score` == 0.5."""
    if top < min_score:
        return max(0.0, top / min_score * 0.5)
    return min(1.0, 0.5 + (top - min_score) / (0.72 - min_score) * 0.5)


def _extractive_answer(hits: list[dict], section_text) -> str:
    best = hits[0]
    lines = [f"Here is what the approved knowledge base says ({best['title']} - {best['section']}):", ""]
    lines.append(_tidy(section_text(best["article_id"], best["section"]) or best["text"]))
    for h in hits[1:3]:
        if h["article_id"] == best["article_id"] and h["section"] != best["section"] and h["section"] not in ("Symptoms", "Overview"):
            lines += ["", f"**{h['section']}**", _tidy(section_text(h["article_id"], h["section"]) or h["text"])]
            break
    return "\n".join(lines)


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _ensure_citations(answer: str, hits: list[dict]) -> str:
    if re.search(r"\[KB\d{4}\]", answer):
        return answer
    ids = list(dict.fromkeys(h["article_id"] for h in hits))
    return f"{answer}\n\nSources: " + ", ".join(f"[{i}]" for i in ids)


_rag: RAGService | None = None


def get_rag() -> RAGService:
    global _rag
    if _rag is None:
        _rag = RAGService()
    return _rag
