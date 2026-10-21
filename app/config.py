"""Application settings, loaded from environment variables / .env (never commit secrets)."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI ITSM Helpdesk API"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- MongoDB Atlas -------------------------------------------------------------
    # Atlas: mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "itsm_helpdesk"
    # "auto": try MONGODB_URI, fall back to in-memory mongomock if unreachable (demo safety net)
    db_mode: Literal["auto", "mongodb", "memory"] = "auto"

    # --- Embeddings / vector store ------------------------------------------------
    embedding_backend: Literal["sentence-transformers", "hashing"] = "sentence-transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    kb_dir: Path = BASE_DIR / "knowledge_base"
    vector_store_dir: Path = BASE_DIR / "data" / "vector_store"
    chunk_size_words: int = 160
    chunk_overlap_words: int = 30
    rag_top_k: int = 4
    # Minimum cosine similarity for a chunk to count as approved, relevant knowledge
    rag_min_score: float = 0.45

    # --- LLM (Hugging Face) ------------------------------------------------------------
    # local       -> transformers pipeline on this machine (default: Qwen2.5-0.5B-Instruct)
    # hf_inference-> Hugging Face Inference Providers API (needs HF_TOKEN)
    # extractive  -> no LLM, deterministic extractive answers (offline / tests)
    llm_provider: Literal["local", "hf_inference", "extractive"] = "local"
    llm_local_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    llm_hf_model: str = "Qwen/Qwen2.5-7B-Instruct"
    hf_token: str | None = None
    llm_max_new_tokens: int = 320
    llm_device: Literal["auto", "cpu", "mps", "cuda"] = "cpu"

    # --- AI governance -------------------------------------------------------------------
    # Below this overall confidence the request is escalated to a human (Service Desk)
    confidence_threshold: float = 0.60

    # --- ServiceNow ------------------------------------------------------------------------
    servicenow_mode: Literal["mock", "live"] = "mock"
    servicenow_instance: str | None = None  # e.g. https://dev12345.service-now.com
    servicenow_user: str | None = None
    servicenow_password: str | None = None

    # --- Provisioning simulation ------------------------------------------------------
    provisioning_step_seconds: float = 6.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
