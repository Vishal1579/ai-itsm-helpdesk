"""MongoDB (Atlas) access via Motor, with an in-memory fallback for offline demos and tests."""
import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

log = logging.getLogger(__name__)

# Collections used by the platform
TICKETS = "tickets"
USERS = "users"
KNOWLEDGE = "knowledge_articles"
KB_CHUNKS = "knowledge_chunks"
KNOWLEDGE_GAPS = "knowledge_gaps"
CHAT = "chat_history"
AUTOMATION = "automation_actions"
SOFTWARE_REQUESTS = "software_requests"
SOFTWARE_CATALOG = "software_catalog"
AUDIT = "audit_logs"
SNOW_MOCK = "servicenow_mock_records"
COUNTERS = "counters"


class Database:
    client = None
    db: AsyncIOMotorDatabase | None = None
    mode: str = "uninitialised"


_state = Database()


async def connect() -> None:
    settings = get_settings()
    if settings.db_mode in ("auto", "mongodb"):
        try:
            client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=4000, tz_aware=True)
            await client.admin.command("ping")
            _state.client, _state.db = client, client[settings.mongodb_db]
            _state.mode = "mongodb-atlas" if "mongodb+srv" in settings.mongodb_uri else "mongodb"
            log.info("Connected to MongoDB (%s)", _state.mode)
            await _ensure_indexes()
            return
        except Exception as exc:  # pragma: no cover - depends on environment
            if settings.db_mode == "mongodb":
                raise
            log.warning("MongoDB unreachable (%s) - falling back to in-memory store", exc)
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient(tz_aware=True)
    _state.client, _state.db, _state.mode = client, client[settings.mongodb_db], "in-memory"


async def _ensure_indexes() -> None:
    db = get_db()
    await db[TICKETS].create_index("ticket_id", unique=True)
    await db[TICKETS].create_index([("created_at", -1)])
    await db[AUDIT].create_index([("timestamp", -1)])
    await db[AUDIT].create_index("ticket_id")
    await db[CHAT].create_index([("session_id", 1), ("timestamp", 1)])
    await db[SOFTWARE_REQUESTS].create_index("request_number", unique=True)
    await db[SNOW_MOCK].create_index([("table", 1), ("number", 1)], unique=True)


async def close() -> None:
    if _state.client is not None and hasattr(_state.client, "close"):
        _state.client.close()


def get_db() -> AsyncIOMotorDatabase:
    if _state.db is None:
        raise RuntimeError("Database not initialised")
    return _state.db


def db_mode() -> str:
    return _state.mode


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def next_sequence(name: str, start: int) -> int:
    """Atomic counter used for human-readable ids (INC/REQ/RITM numbers)."""
    from pymongo import ReturnDocument

    doc = await get_db()[COUNTERS].find_one_and_update(
        {"_id": name}, {"$inc": {"value": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return start + doc["value"]


def clean(doc: dict | None) -> dict | None:
    """Strip Mongo's ObjectId so documents serialise to JSON."""
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc
