"""FAISS vector store (exact inner-product search over normalised embeddings), persisted to disk."""
import json
import logging
import threading
from dataclasses import asdict
from pathlib import Path

import faiss

faiss.omp_set_num_threads(1)  # tiny index; avoids OpenMP contention with torch
import numpy as np

from app.rag.chunking import Chunk

log = logging.getLogger(__name__)


class FaissVectorStore:
    def __init__(self, directory: Path, dim: int) -> None:
        self.directory = directory
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.chunks: list[Chunk] = []
        self.fingerprint: str | None = None
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return self.index.ntotal

    def rebuild(self, chunks: list[Chunk], vectors: np.ndarray, fingerprint: str) -> None:
        with self._lock:
            self.index = faiss.IndexFlatIP(self.dim)
            if len(chunks):
                self.index.add(vectors)
            self.chunks = list(chunks)
            self.fingerprint = fingerprint
            self.save()

    def search(self, query_vec: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        if self.size == 0:
            return []
        scores, ids = self.index.search(query_vec.reshape(1, -1), min(k, self.size))
        return [(self.chunks[i], float(s)) for s, i in zip(scores[0], ids[0]) if i >= 0]

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.directory / "kb.faiss"))
        meta = {"fingerprint": self.fingerprint, "dim": self.dim, "chunks": [asdict(c) for c in self.chunks]}
        (self.directory / "kb_chunks.json").write_text(json.dumps(meta, indent=1))

    def load(self) -> bool:
        idx_path, meta_path = self.directory / "kb.faiss", self.directory / "kb_chunks.json"
        if not (idx_path.exists() and meta_path.exists()):
            return False
        try:
            meta = json.loads(meta_path.read_text())
            if meta.get("dim") != self.dim:
                return False
            self.index = faiss.read_index(str(idx_path))
            self.chunks = [Chunk(**c) for c in meta["chunks"]]
            self.fingerprint = meta.get("fingerprint")
            return self.index.ntotal == len(self.chunks)
        except Exception as exc:  # pragma: no cover
            log.warning("Could not load vector store: %s", exc)
            return False
