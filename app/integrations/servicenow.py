"""ServiceNow integration.

Two interchangeable clients share one interface:
  * LiveServiceNowClient - ServiceNow REST Table API (`/api/now/table/{table}`) with basic auth.
  * MockServiceNowClient - stores records in MongoDB using ServiceNow's field names, numbering
                           (INC0010001 / REQ0001245 / RITM0001245) and state codes, so switching
                           SERVICENOW_MODE=live needs no code changes.

AI output -> ServiceNow field mapping (see map_incident_fields):
  summary -> short_description         category/subcategory -> category/subcategory
  description + AI analysis -> description / work_notes
  impact/urgency -> impact/urgency (1-3); ServiceNow derives priority from them
  assignment group -> assignment_group (display value)
  caller -> caller_id, channel -> contact_type=self-service
"""
import logging
import uuid
from typing import Any, Protocol

import httpx

from app.ai.taxonomy import IMPACT_TO_SN, PRIORITY_LABELS, PRIORITY_MATRIX, URGENCY_TO_SN
from app.audit import audit
from app.config import get_settings
from app.db import SNOW_MOCK, clean, get_db, next_sequence, utcnow

log = logging.getLogger(__name__)

INCIDENT_STATES = {"1": "New", "2": "In Progress", "3": "On Hold", "6": "Resolved", "7": "Closed", "8": "Canceled"}
REQUEST_STATES = {"1": "Open", "2": "Work in Progress", "3": "Closed Complete", "4": "Closed Incomplete"}
PREFIX = {"incident": ("INC", 10000, 7), "sc_request": ("REQ", 1244, 7), "sc_req_item": ("RITM", 1244, 7)}


class ServiceNowClient(Protocol):
    mode: str

    async def create_record(self, table: str, fields: dict) -> dict: ...
    async def get_record(self, table: str, number_or_sys_id: str) -> dict | None: ...
    async def update_record(self, table: str, sys_id: str, fields: dict) -> dict: ...
    async def list_records(self, table: str, limit: int = 50) -> list[dict]: ...


def map_incident_fields(analysis: dict, description: str, caller: str) -> dict:
    """Map AI-generated triage onto ServiceNow incident fields."""
    return {
        "short_description": analysis["summary"],
        "description": description,
        "category": analysis["category"].lower(),
        "subcategory": analysis["subcategory"].lower(),
        "impact": IMPACT_TO_SN[analysis["impact"]],
        "urgency": URGENCY_TO_SN[analysis["urgency"]],
        "assignment_group": analysis["assignment_group"],
        "caller_id": caller,
        "contact_type": "self-service",
        "u_ai_intent": analysis["intent"],
        "u_ai_confidence": str(analysis["confidence"]),
        "work_notes": (
            f"[AI Triage] intent={analysis['intent']} category={analysis['category']}/{analysis['subcategory']} "
            f"priority={analysis['priority']} confidence={analysis['confidence']:.2f}. "
            f"Suggested resolution: {analysis['suggested_resolution']}"
            + (f" (KB {analysis['kb_article']})" if analysis.get("kb_article") else "")
        ),
    }


def _priority_from(impact: str, urgency: str) -> str:
    """Mirror of the instance's priority data-lookup rule (customised to the org's ITIL matrix)."""
    imp = {v: k for k, v in IMPACT_TO_SN.items()}.get(str(impact), "Individual")
    urg = {v: k for k, v in URGENCY_TO_SN.items()}.get(str(urgency), "Low")
    return PRIORITY_LABELS[PRIORITY_MATRIX[(imp, urg)]]


class MockServiceNowClient:
    mode = "mock"

    async def create_record(self, table: str, fields: dict) -> dict:
        prefix, start, width = PREFIX.get(table, ("REC", 0, 7))
        n = await next_sequence(f"snow_{table}", start)
        now = utcnow()
        record = {
            "table": table,
            "sys_id": uuid.uuid4().hex,
            "number": f"{prefix}{n:0{width}d}",
            "sys_created_on": now.isoformat(),
            "sys_updated_on": now.isoformat(),
            "sys_created_by": "ai.helpdesk.integration",
            "state": fields.pop("state", "1"),
            "work_notes_history": [],
            **fields,
        }
        if table == "incident":
            record["priority"] = _priority_from(record.get("impact", "3"), record.get("urgency", "3"))
        if record.get("work_notes"):
            record["work_notes_history"].append({"at": now.isoformat(), "note": record.pop("work_notes")})
        record["state_label"] = _state_label(table, record["state"])
        await get_db()[SNOW_MOCK].insert_one(dict(record))
        return clean(record)

    async def get_record(self, table: str, number_or_sys_id: str) -> dict | None:
        q = {"table": table, "$or": [{"number": number_or_sys_id}, {"sys_id": number_or_sys_id}]}
        return clean(await get_db()[SNOW_MOCK].find_one(q))

    async def update_record(self, table: str, sys_id: str, fields: dict) -> dict:
        fields = dict(fields)
        note = fields.pop("work_notes", None)
        now = utcnow().isoformat()
        update: dict[str, Any] = {"$set": {**fields, "sys_updated_on": now}}
        if "state" in fields:
            update["$set"]["state_label"] = _state_label(table, fields["state"])
        if note:
            update["$push"] = {"work_notes_history": {"at": now, "note": note}}
        db = get_db()
        await db[SNOW_MOCK].update_one({"table": table, "sys_id": sys_id}, update)
        return clean(await db[SNOW_MOCK].find_one({"table": table, "sys_id": sys_id}))

    async def list_records(self, table: str, limit: int = 50) -> list[dict]:
        cur = get_db()[SNOW_MOCK].find({"table": table}).sort("sys_created_on", -1).limit(limit)
        return [clean(d) for d in await cur.to_list(limit)]


class LiveServiceNowClient:
    """ServiceNow REST Table API client (tested against a Personal Developer Instance)."""

    mode = "live"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.servicenow_instance and s.servicenow_user and s.servicenow_password):
            raise ValueError("SERVICENOW_INSTANCE, SERVICENOW_USER and SERVICENOW_PASSWORD are required in live mode")
        self.base = s.servicenow_instance.rstrip("/") + "/api/now/table"
        self.auth = (s.servicenow_user, s.servicenow_password)
        self.params = {"sysparm_display_value": "false", "sysparm_input_display_value": "true", "sysparm_exclude_reference_link": "true"}

    async def _request(self, method: str, url: str, **kw) -> dict:
        async with httpx.AsyncClient(auth=self.auth, timeout=20, headers={"Accept": "application/json"}) as client:
            resp = await client.request(method, url, params={**self.params, **kw.pop("params", {})}, **kw)
            resp.raise_for_status()
            return resp.json()

    async def create_record(self, table: str, fields: dict) -> dict:
        data = await self._request("POST", f"{self.base}/{table}", json=fields)
        return _normalise_live(table, data["result"])

    async def get_record(self, table: str, number_or_sys_id: str) -> dict | None:
        key = "number" if number_or_sys_id[:3].isalpha() else "sys_id"
        data = await self._request("GET", f"{self.base}/{table}", params={"sysparm_query": f"{key}={number_or_sys_id}", "sysparm_limit": "1"})
        return _normalise_live(table, data["result"][0]) if data["result"] else None

    async def update_record(self, table: str, sys_id: str, fields: dict) -> dict:
        data = await self._request("PATCH", f"{self.base}/{table}/{sys_id}", json=fields)
        return _normalise_live(table, data["result"])

    async def list_records(self, table: str, limit: int = 50) -> list[dict]:
        data = await self._request("GET", f"{self.base}/{table}", params={"sysparm_limit": str(limit), "sysparm_query": "ORDERBYDESCsys_created_on"})
        return [_normalise_live(table, r) for r in data["result"]]


def _state_label(table: str, state: str) -> str:
    return (INCIDENT_STATES if table == "incident" else REQUEST_STATES).get(str(state), str(state))


def _normalise_live(table: str, rec: dict) -> dict:
    rec = dict(rec)
    rec["table"] = table
    rec["state_label"] = _state_label(table, rec.get("state", ""))
    return rec


class AuditedServiceNow:
    """Wraps either client so every ServiceNow call lands in the audit log."""

    def __init__(self, client: ServiceNowClient) -> None:
        self.client = client
        self.mode = client.mode

    async def create_incident(self, fields: dict, ticket_id: str | None = None) -> dict:
        rec = await self.client.create_record("incident", dict(fields))
        await audit("servicenow.incident.create", actor="integration", ticket_id=ticket_id,
                    details={"number": rec["number"], "sys_id": rec["sys_id"], "mode": self.mode, "fields": _safe(fields)})
        return rec

    async def get_incident(self, number_or_sys_id: str) -> dict | None:
        return await self.client.get_record("incident", number_or_sys_id)

    async def update_incident(self, sys_id: str, fields: dict, ticket_id: str | None = None) -> dict:
        rec = await self.client.update_record("incident", sys_id, fields)
        await audit("servicenow.incident.update", actor="integration", ticket_id=ticket_id,
                    details={"number": rec.get("number"), "mode": self.mode, "fields": _safe(fields)})
        return rec

    async def create_request(self, fields: dict, item_fields: dict, ticket_id: str | None = None) -> tuple[dict, dict]:
        """Service request = sc_request (REQ) + one requested item (RITM)."""
        req = await self.client.create_record("sc_request", dict(fields))
        ritm = await self.client.create_record("sc_req_item", {**item_fields, "request": req["sys_id"], "request_number": req["number"]})
        await audit("servicenow.request.create", actor="integration", ticket_id=ticket_id,
                    details={"number": req["number"], "ritm": ritm["number"], "mode": self.mode, "fields": _safe(fields)})
        return req, ritm

    async def update_request(self, sys_id: str, fields: dict, ticket_id: str | None = None) -> dict:
        rec = await self.client.update_record("sc_request", sys_id, fields)
        await audit("servicenow.request.update", actor="integration", ticket_id=ticket_id,
                    details={"number": rec.get("number"), "mode": self.mode, "fields": _safe(fields)})
        return rec

    async def update_request_item(self, sys_id: str, fields: dict) -> dict:
        return await self.client.update_record("sc_req_item", sys_id, fields)

    async def get_request(self, number_or_sys_id: str) -> dict | None:
        return await self.client.get_record("sc_request", number_or_sys_id)

    async def list(self, table: str, limit: int = 50) -> list[dict]:
        return await self.client.list_records(table, limit)


def _safe(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if "password" not in k.lower()}


_sn: AuditedServiceNow | None = None


def get_servicenow() -> AuditedServiceNow:
    global _sn
    if _sn is None:
        mode = get_settings().servicenow_mode
        client: ServiceNowClient
        if mode == "live":
            try:
                client = LiveServiceNowClient()
            except ValueError as exc:
                log.warning("%s - using mock ServiceNow", exc)
                client = MockServiceNowClient()
        else:
            client = MockServiceNowClient()
        _sn = AuditedServiceNow(client)
    return _sn
