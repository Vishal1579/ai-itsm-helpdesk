"""FastAPI entrypoint: `uvicorn app.main:app --reload`"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.ai.classifier import get_classifier
from app.ai.llm import get_llm
from app.config import get_settings
from app.mock_apis import automation as auto_api
from app.rag.service import get_rag
from app.routers import api, mock_apis
from app.seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("itsm")
for noisy in ("httpx", "huggingface_hub", "sentence_transformers"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    await seed()
    auto_api.reset_state()
    rag = get_rag()
    await rag.sync_from_disk()
    stats = await rag.build_index()
    get_classifier()._ensure_vectors()
    log.info("Ready - db=%s rag=%s llm=%s", db.db_mode(), stats, get_llm().info())
    # Load the local LLM in the background so the first chat isn't slow
    asyncio.get_running_loop().run_in_executor(None, get_llm().warmup)
    yield
    await db.close()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="AI-powered ITSM helpdesk: intelligent intake, self-heal automation, RAG knowledge base, "
                "self-service chatbot and software provisioning with ServiceNow integration.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(api.router)
app.include_router(mock_apis.router)


@app.get("/")
async def root():
    return {"service": settings.app_name, "docs": "/docs", "health": "/api/health"}
