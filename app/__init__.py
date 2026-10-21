import os

# PyTorch and FAISS each ship an OpenMP runtime; on macOS loading both segfaults unless allowed.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# torch must be loaded before faiss on macOS/arm64, otherwise the two OpenMP runtimes segfault.
try:  # pragma: no cover - import side effect only
    import torch  # noqa: F401
except ImportError:  # hashing-embedding / extractive mode without torch installed
    pass
