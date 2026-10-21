"""Text embeddings: sentence-transformers (default) with a dependency-free hashing fallback."""
import hashlib
import logging
import re
import threading

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)


class Embedder:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        settings = get_settings()
        self.backend = settings.embedding_backend
        self.model_name = settings.embedding_model if self.backend == "sentence-transformers" else "hashing-512"

    def _load(self):
        with self._lock:
            if self._model is None and self.backend == "sentence-transformers":
                try:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self.model_name, device="cpu")
                except Exception as exc:  # pragma: no cover - offline environments
                    log.warning("Could not load %s (%s); using hashing embeddings", self.model_name, exc)
                    self.backend, self.model_name = "hashing", "hashing-512"
        return self._model

    @property
    def dim(self) -> int:
        if self.backend == "hashing":
            return 512
        model = self._load()
        if model is None:
            return 512
        fn = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        return fn()

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return L2-normalised float32 vectors so inner product == cosine similarity."""
        if self.backend == "sentence-transformers":
            model = self._load()
            if model is not None:
                vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                return np.asarray(vecs, dtype="float32")
        return np.vstack([_hash_embed(t) for t in texts]).astype("float32")


def _hash_embed(text: str, dim: int = 512) -> np.ndarray:
    vec = np.zeros(dim, dtype="float32")
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
