"""Immutable audit trail: every AI decision, automated action and ServiceNow call is recorded."""
import uuid
from typing import Any

from app.db import AUDIT, get_db, utcnow


async def audit(
    action: str,
    *,
    actor: str = "ai-agent",
    ticket_id: str | None = None,
    status: str = "success",
    details: dict[str, Any] | None = None,
) -> dict:
    entry = {
        "audit_id": uuid.uuid4().hex[:12],
        "timestamp": utcnow(),
        "actor": actor,
        "action": action,
        "ticket_id": ticket_id,
        "status": status,
        "details": details or {},
    }
    await get_db()[AUDIT].insert_one(dict(entry))
    return entry
