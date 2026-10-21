"""Public REST API consumed by the React portal."""
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents import provisioning
from app.ai.classifier import get_classifier
from app.ai.llm import get_llm
from app.audit import audit
from app.config import get_settings
from app.db import (
    AUDIT, AUTOMATION, CHAT, KNOWLEDGE, KNOWLEDGE_GAPS, SOFTWARE_CATALOG, SOFTWARE_REQUESTS, TICKETS, USERS,
    clean, db_mode, get_db, utcnow,
)
from app.integrations.servicenow import get_servicenow
from app.mock_apis.catalog import catalog_terms
from app.orchestrator import escalate_ticket, handle_message
from app.rag.chunking import KnowledgeDoc
from app.rag.service import get_rag
from app.tickets import get_ticket, update_ticket

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ models
class ChatIn(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    user_id: str = "emp001"
    session_id: str | None = None


class TicketIn(BaseModel):
    description: str = Field(min_length=5, max_length=4000)
    user_id: str = "emp001"
    request_type: Literal["auto", "incident", "service_request"] = "auto"


class TicketPatch(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed", "escalated"] | None = None
    work_note: str | None = None


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class ArticleIn(BaseModel):
    title: str = Field(min_length=5)
    category: str
    subcategory: str
    content: str = Field(min_length=40)
    tags: list[str] = []
    owner: str = "Service Desk"


class ApprovalIn(BaseModel):
    approved: bool = True
    approver: str = "line.manager"


# ------------------------------------------------------------------ health
@router.get("/health")
async def health():
    s = get_settings()
    return {
        "status": "ok",
        "database": db_mode(),
        "llm": get_llm().info(),
        "rag": get_rag().stats(),
        "servicenow": {"mode": get_servicenow().mode, "instance": s.servicenow_instance if get_servicenow().mode == "live" else "mock"},
        "confidence_threshold": s.confidence_threshold,
        "rag_min_score": s.rag_min_score,
    }


@router.get("/users")
async def users():
    return [clean(u) for u in await get_db()[USERS].find({}).to_list(None)]


# ------------------------------------------------------------------ chat / intake
@router.post("/chat")
async def chat(body: ChatIn):
    return await handle_message(body.message, body.user_id, body.session_id, channel="chat")


@router.get("/chat/{session_id}")
async def chat_history(session_id: str):
    return [clean(m) for m in await get_db()[CHAT].find({"session_id": session_id}).sort("timestamp", 1).to_list(500)]


@router.post("/analyze")
async def analyze(body: AskIn):
    """Dry-run triage: classification only, nothing is created."""
    catalog = await get_db()[SOFTWARE_CATALOG].find({}).to_list(None)
    return get_classifier().classify(body.question, catalog_terms([clean(c) for c in catalog])).to_dict()


# ------------------------------------------------------------------ tickets
@router.post("/tickets")
async def create_ticket(body: TicketIn):
    force = None if body.request_type == "auto" else body.request_type
    return await handle_message(body.description, body.user_id, channel="portal", force_intent=force)


@router.get("/tickets")
async def list_tickets(type: str | None = None, status: str | None = None, user_id: str | None = None, limit: int = Query(100, le=500)):
    q = {k: v for k, v in {"type": type, "status": status, "user_id": user_id}.items() if v}
    return [clean(t) for t in await get_db()[TICKETS].find(q).sort("created_at", -1).limit(limit).to_list(limit)]


@router.get("/tickets/{ticket_id}")
async def ticket_detail(ticket_id: str):
    t = await get_ticket(ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    t["audit"] = [clean(a) for a in await get_db()[AUDIT].find({"ticket_id": ticket_id}).sort("timestamp", 1).to_list(200)]
    if t.get("software_request"):
        t["software_request"] = clean(await get_db()[SOFTWARE_REQUESTS].find_one({"request_number": t["software_request"]["request_number"]})) or t["software_request"]
    return t


@router.post("/tickets/{ticket_id}/escalate")
async def escalate(ticket_id: str):
    try:
        return await escalate_ticket(ticket_id)
    except KeyError:
        raise HTTPException(404, "Ticket not found")


@router.patch("/tickets/{ticket_id}")
async def patch_ticket(ticket_id: str, body: TicketPatch):
    t = await get_ticket(ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    sn_fields = {}
    if body.status:
        sn_fields["state"] = {"open": "1", "in_progress": "2", "resolved": "6", "closed": "7", "escalated": "2"}[body.status]
        if body.status == "resolved":
            sn_fields.update(close_code="Solved (Permanently)", close_notes=body.work_note or "Resolved by analyst")
    if body.work_note:
        sn_fields["work_notes"] = body.work_note
    sn = t.get("servicenow")
    if sn and sn.get("table") == "incident" and sn_fields:
        rec = await get_servicenow().update_incident(sn["sys_id"], sn_fields, ticket_id)
        sn = {**sn, "state": rec.get("state"), "state_label": rec.get("state_label")}
    fields = {"servicenow": sn}
    if body.status:
        fields["status"] = body.status
        if body.status == "resolved" and not t.get("resolved_by"):
            fields["resolved_by"] = "human"
    await audit("ticket.updated", actor="analyst", ticket_id=ticket_id, details=body.model_dump(exclude_none=True))
    return await update_ticket(ticket_id, fields, "updated", body.work_note or f"status -> {body.status}")


# ------------------------------------------------------------------ ServiceNow passthrough
@router.get("/servicenow/{table}")
async def sn_list(table: Literal["incident", "sc_request", "sc_req_item"], limit: int = 50):
    return await get_servicenow().list(table, limit)


@router.get("/servicenow/incident/{number}")
async def sn_get_incident(number: str):
    rec = await get_servicenow().get_incident(number)
    if not rec:
        raise HTTPException(404, "Incident not found in ServiceNow")
    return rec


# ------------------------------------------------------------------ knowledge base
@router.get("/kb/articles")
async def kb_articles(category: str | None = None, q: str | None = None):
    query: dict = {"status": "published"}
    if category:
        query["category"] = category
    arts = [clean(a) for a in await get_db()[KNOWLEDGE].find(query, {"content": 0}).sort("article_id", 1).to_list(None)]
    if q:
        rx = re.compile(re.escape(q), re.I)
        arts = [a for a in arts if rx.search(a["title"]) or rx.search(" ".join(a.get("tags", []))) or rx.search(a.get("summary", ""))]
    return arts


@router.get("/kb/categories")
async def kb_categories():
    arts = await get_db()[KNOWLEDGE].find({"status": "published"}, {"category": 1}).to_list(None)
    counts: dict[str, int] = {}
    for a in arts:
        counts[a["category"]] = counts.get(a["category"], 0) + 1
    return [{"category": k, "count": v} for k, v in sorted(counts.items())]


@router.get("/kb/articles/{article_id}")
async def kb_article(article_id: str):
    db = get_db()
    art = clean(await db[KNOWLEDGE].find_one({"article_id": article_id}))
    if not art:
        raise HTTPException(404, "Article not found")
    await db[KNOWLEDGE].update_one({"article_id": article_id}, {"$inc": {"views": 1}})
    return art


@router.get("/kb/search")
async def kb_search(q: str = Query(min_length=2), k: int = Query(5, le=10)):
    """Raw semantic search over the vector store (shows similarity scores)."""
    return {"query": q, "min_score": get_settings().rag_min_score, "results": await get_rag().search(q, k)}


@router.post("/kb/ask")
async def kb_ask(body: AskIn):
    return await get_rag().answer(body.question)


@router.post("/kb/articles")
async def kb_create(body: ArticleIn):
    """Knowledge management automation: new articles are chunked, embedded and indexed immediately."""
    existing = await get_db()[KNOWLEDGE].count_documents({})
    article_id = f"KB{existing + 1:04d}"
    while await get_db()[KNOWLEDGE].find_one({"article_id": article_id}):
        existing += 1
        article_id = f"KB{existing + 1:04d}"
    doc = KnowledgeDoc(article_id=article_id, title=body.title, category=body.category, subcategory=body.subcategory,
                       tags=body.tags, owner=body.owner, body=f"# {body.title}\n\n{body.content}", source_file="portal")
    result = await get_rag().publish_article(doc, author="portal")
    await audit("kb.article.published", actor="knowledge-manager", details={"article_id": article_id, "title": body.title})
    return result


@router.post("/kb/reindex")
async def kb_reindex():
    await get_rag().sync_from_disk()
    stats = await get_rag().build_index(force=True)
    await audit("kb.reindex", actor="system", details=stats)
    return stats


@router.get("/kb/gaps")
async def kb_gaps():
    return [clean(g) for g in await get_db()[KNOWLEDGE_GAPS].find({}).sort("created_at", -1).to_list(100)]


@router.post("/kb/drafts/from-ticket/{ticket_id}")
async def kb_draft_from_ticket(ticket_id: str):
    """Knowledge management automation: draft a KB article from a resolved/escalated ticket for human review."""
    t = await get_ticket(ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    a = t["analysis"]
    notes = []
    if t.get("automation"):
        notes = [f"{i + 1}. {s['step']}: {s['detail']}" for i, s in enumerate(t["automation"]["steps"])]
    llm_text = await get_llm().generate(
        "You write concise IT knowledge base articles in markdown with sections: Symptoms, Resolution steps, When to escalate. "
        "Only use the facts provided.",
        f"Issue: {t['description']}\nCategory: {a['category']}/{a['subcategory']}\nResolution notes:\n" + ("\n".join(notes) or a["suggested_resolution"]),
        max_new_tokens=280,
    )
    content = llm_text or (
        f"## Symptoms\n{t['description']}\n\n## Resolution steps\n" + ("\n".join(notes) or f"1. {a['suggested_resolution']}")
        + f"\n\n## When to escalate\nContact {a['assignment_group']} if the steps above do not resolve the issue."
    )
    return {"status": "draft", "title": a["summary"], "category": a["category"], "subcategory": a["subcategory"],
            "content": content, "source_ticket": ticket_id, "generated_by": get_llm().model_name if llm_text else "template"}


# ------------------------------------------------------------------ catalogue & requests
@router.get("/catalog")
async def catalog():
    return [clean(c) for c in await get_db()[SOFTWARE_CATALOG].find({}).sort("name", 1).to_list(None)]


@router.get("/requests")
async def software_requests(user_id: str | None = None):
    q = {"user_id": user_id} if user_id else {}
    return [clean(r) for r in await get_db()[SOFTWARE_REQUESTS].find(q).sort("created_at", -1).to_list(200)]


@router.get("/requests/{request_number}")
async def software_request(request_number: str):
    r = clean(await get_db()[SOFTWARE_REQUESTS].find_one({"request_number": request_number}))
    if not r:
        raise HTTPException(404, "Request not found")
    return r


@router.post("/requests/{request_number}/approve")
async def approve_request(request_number: str, body: ApprovalIn):
    try:
        return await provisioning.approve(request_number, body.approver, body.approved)
    except KeyError:
        raise HTTPException(404, "Request not found")


# ------------------------------------------------------------------ audit & automation
@router.get("/audit")
async def audit_log(ticket_id: str | None = None, limit: int = Query(200, le=1000)):
    q = {"ticket_id": ticket_id} if ticket_id else {}
    return [clean(a) for a in await get_db()[AUDIT].find(q).sort("timestamp", -1).limit(limit).to_list(limit)]


@router.get("/automation/runs")
async def automation_runs(limit: int = 50):
    rows = [clean(r) for r in await get_db()[AUTOMATION].find({}).sort("at", -1).limit(limit * 7).to_list(None)]
    runs: dict[str, dict] = {}
    for r in reversed(rows):
        run = runs.setdefault(r["run_id"], {"run_id": r["run_id"], "ticket_id": r["ticket_id"], "playbook": r["playbook"], "steps": [], "started_at": r["at"]})
        run["steps"].append(r)
    return sorted(runs.values(), key=lambda x: x["started_at"], reverse=True)[:limit]


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard/stats")
async def dashboard():
    db = get_db()
    tickets = await db[TICKETS].find({}, {"timeline": 0, "rag.answer": 0}).to_list(None)
    reqs = await db[SOFTWARE_REQUESTS].find({}, {"history": 0}).to_list(None)
    runs = await automation_runs(500)

    def count(pred):
        return sum(1 for t in tickets if pred(t))

    by = lambda key: _group(tickets, key)  # noqa: E731
    open_states = {"new", "open", "in_progress", "escalated", "provisioning", "awaiting_approval", "awaiting_user"}
    outcomes = {"resolved": 0, "escalated": 0, "blocked": 0}
    for r in runs:
        last = r["steps"][-1]["detail"] if r["steps"] else ""
        if any(s["step"] == "Determine Automation" and s["status"] == "blocked" for s in r["steps"]):
            outcomes["blocked"] += 1
        elif "Resolved" in last:
            outcomes["resolved"] += 1
        else:
            outcomes["escalated"] += 1
    total = len(tickets)
    ai_resolved = count(lambda t: t.get("resolved_by") == "ai")
    confs = [t["analysis"]["confidence"] for t in tickets if t.get("analysis")]
    return {
        "totals": {
            "total": total,
            "open": count(lambda t: t["status"] in open_states),
            "ai_resolved": ai_resolved,
            "escalated": count(lambda t: t.get("escalated")),
            "incidents": count(lambda t: t["type"] == "incident"),
            "knowledge": count(lambda t: t["type"] == "knowledge"),
            "service_requests": count(lambda t: t["type"] == "service_request"),
            "software_requests": len(reqs),
            "automation_runs": len(runs),
            "deflection_rate": round(ai_resolved / total, 3) if total else 0,
            "avg_confidence": round(sum(confs) / len(confs), 3) if confs else 0,
            "knowledge_gaps": await db[KNOWLEDGE_GAPS].count_documents({"status": "open"}),
        },
        "by_intent": _group([t["analysis"] for t in tickets if t.get("analysis")], "intent"),
        "by_category": _group([t["analysis"] for t in tickets if t.get("analysis")], "category"),
        "by_priority": _group([t["analysis"] for t in tickets if t.get("analysis") and t["type"] == "incident"], "priority"),
        "by_status": by("status"),
        "software_by_status": _group(reqs, "status"),
        "automation": {"outcomes": outcomes, "by_playbook": _group(runs, "playbook"),
                       "recent": [{"run_id": r["run_id"], "ticket_id": r["ticket_id"], "playbook": r["playbook"], "started_at": r["started_at"],
                                   "status": r["steps"][-1]["status"] if r["steps"] else "unknown", "steps": len(r["steps"])} for r in runs[:8]]},
        "recent_tickets": [_brief(clean(t)) for t in sorted(tickets, key=lambda t: t["created_at"], reverse=True)[:10]],
        "generated_at": utcnow(),
    }


def _group(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        v = r.get(key) or "unknown"
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _brief(t: dict) -> dict:
    a = t.get("analysis") or {}
    return {"ticket_id": t["ticket_id"], "type": t["type"], "status": t["status"], "summary": a.get("summary"), "priority": a.get("priority"),
            "intent": a.get("intent"), "confidence": a.get("confidence"), "created_at": t["created_at"], "escalated": t.get("escalated"),
            "resolved_by": t.get("resolved_by"), "servicenow": (t.get("servicenow") or {}).get("number")}


# ------------------------------------------------------------------ demo admin
@router.post("/admin/reset-demo")
async def reset_demo():
    """Clear transactional demo data (tickets, chats, audit, requests, mock ServiceNow) and reset mock systems."""
    from app.db import COUNTERS, SNOW_MOCK
    from app.mock_apis import automation as auto_api

    db = get_db()
    for col in (TICKETS, CHAT, AUDIT, AUTOMATION, SOFTWARE_REQUESTS, SNOW_MOCK, KNOWLEDGE_GAPS, COUNTERS):
        await db[col].delete_many({})
    auto_api.reset_state()
    return {"status": "demo data reset"}
