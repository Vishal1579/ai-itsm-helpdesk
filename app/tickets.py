"""Local ticket store (MongoDB) - the platform's record of every request and how AI handled it."""
import uuid

from app.db import TICKETS, USERS, clean, get_db, utcnow

DEMO_USERS = [
    {"user_id": "emp001", "name": "Jordan Lee", "email": "jordan.lee@corp.example.com", "department": "Finance", "device": "LT-1001", "location": "London", "role": "employee"},
    {"user_id": "emp002", "name": "Sam Patel", "email": "sam.patel@corp.example.com", "department": "Engineering", "device": "LT-2042", "location": "Bengaluru", "role": "employee"},
    {"user_id": "adm001", "name": "Alex Kim", "email": "alex.kim@corp.example.com", "department": "IT Operations", "device": "LT-0007", "location": "New York", "role": "privileged"},
]


async def get_user(user_id: str) -> dict:
    user = clean(await get_db()[USERS].find_one({"user_id": user_id}))
    return user or {**DEMO_USERS[0], "user_id": user_id, "name": user_id}


async def new_ticket(kind: str, description: str, user: dict, channel: str, analysis: dict) -> dict:
    now = utcnow()
    ticket = {
        "ticket_id": f"TKT-{uuid.uuid4().hex[:6].upper()}",
        "type": kind,
        "channel": channel,
        "user_id": user["user_id"],
        "user_name": user.get("name"),
        "description": description,
        "status": "new",
        "resolved_by": None,
        "escalated": False,
        "escalation_reason": None,
        "analysis": analysis,
        "rag": None,
        "automation": None,
        "diagnostics": None,
        "servicenow": None,
        "software_request": None,
        "timeline": [{"at": now, "event": "created", "detail": f"Received via {channel}"}],
        "created_at": now,
        "updated_at": now,
    }
    await get_db()[TICKETS].insert_one(dict(ticket))
    return ticket


async def update_ticket(ticket_id: str, fields: dict, event: str | None = None, detail: str = "") -> dict:
    update: dict = {"$set": {**fields, "updated_at": utcnow()}}
    if event:
        update["$push"] = {"timeline": {"at": utcnow(), "event": event, "detail": detail}}
    db = get_db()
    await db[TICKETS].update_one({"ticket_id": ticket_id}, update)
    return clean(await db[TICKETS].find_one({"ticket_id": ticket_id}))


async def get_ticket(ticket_id: str) -> dict | None:
    return clean(await get_db()[TICKETS].find_one({"ticket_id": ticket_id}))


def sn_ref(rec: dict) -> dict:
    return {
        "table": rec.get("table"),
        "number": rec.get("number"),
        "sys_id": rec.get("sys_id"),
        "state": rec.get("state"),
        "state_label": rec.get("state_label"),
        "priority": rec.get("priority"),
        "assignment_group": rec.get("assignment_group"),
    }
