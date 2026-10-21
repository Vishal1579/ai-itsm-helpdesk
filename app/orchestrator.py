"""AI orchestrator: Employee Request -> AI Understanding -> Knowledge Retrieval -> Intelligent Decision
-> Automation -> ServiceNow -> Resolution.

Routes each message to one of four workflows:
  knowledge_question -> RAG grounded answer (no answer -> knowledge gap + escalation option)
  incident           -> AI triage + RAG suggested fix + diagnostics + ServiceNow incident
  automatable        -> self-heal agent (falls back to incident when unsafe / low confidence)
  service_request    -> software catalogue + ServiceNow request + mock provisioning
"""
import logging
import uuid

from app.agents.provisioning import request_software
from app.agents.self_heal import PLAYBOOKS, run_self_heal
from app.ai.classifier import get_classifier
from app.ai.taxonomy import GENERAL, find_category
from app.audit import audit
from app.config import get_settings
from app.db import CHAT, KNOWLEDGE_GAPS, SOFTWARE_CATALOG, clean, get_db, utcnow
from app.integrations.servicenow import get_servicenow, map_incident_fields
from app.mock_apis import automation as auto_api
from app.mock_apis.catalog import catalog_terms, match_software
from app.rag.service import get_rag
from app.tickets import get_ticket, get_user, new_ticket, sn_ref, update_ticket

log = logging.getLogger(__name__)

ROUTES = {
    "knowledge_question": "Knowledge Base (RAG)",
    "incident": "Incident Management",
    "automatable": "Self-Heal Automation",
    "service_request": "Service Request / Provisioning",
}


async def handle_message(text: str, user_id: str, session_id: str | None = None, channel: str = "chat",
                         force_intent: str | None = None) -> dict:
    settings = get_settings()
    session_id = session_id or uuid.uuid4().hex
    user = await get_user(user_id)
    await _chat(session_id, user_id, "user", text)

    catalog = [clean(c) for c in await get_db()[SOFTWARE_CATALOG].find({}).to_list(None)]
    software = match_software(text, catalog)
    analysis = get_classifier().classify(text, catalog_terms(catalog)).to_dict()
    if force_intent and force_intent != analysis["intent"]:
        analysis["signals"].append(f"intent overridden by user selection: {force_intent}")
        analysis["intent"] = force_intent
        if force_intent != "automatable":
            analysis["playbook"] = None
    analysis["route"] = ROUTES[analysis["intent"]]
    analysis["threshold"] = settings.confidence_threshold
    if software:
        analysis["software"] = software["name"]

    kind = {"knowledge_question": "knowledge", "automatable": "incident"}.get(analysis["intent"], analysis["intent"])
    ticket = await new_ticket(kind, text, user, channel, analysis)
    await audit("ai.classification", ticket_id=ticket["ticket_id"], details={
        k: analysis[k] for k in ("intent", "category", "subcategory", "priority", "confidence", "assignment_group", "playbook")
    })

    intent = analysis["intent"]
    if intent == "knowledge_question":
        result = await _knowledge(ticket, analysis, text)
    elif intent == "service_request":
        result = await _service_request(ticket, user, analysis, text, software)
    elif intent == "automatable" and analysis["playbook"] in PLAYBOOKS and analysis["confidence"] >= settings.confidence_threshold:
        result = await run_self_heal(ticket, user, analysis, text)
    else:
        result = await _incident(ticket, user, analysis, text)

    ticket = result["ticket"]
    await _chat(session_id, user_id, "assistant", result["reply"], ticket_id=ticket["ticket_id"])
    return {
        "session_id": session_id,
        "reply": result["reply"],
        "intent": analysis["intent"],
        "route": analysis["route"],
        "confidence": analysis["confidence"],
        "escalated": ticket.get("escalated", False),
        "actions": result.get("actions", []),
        "ticket": ticket,
    }


# ---------------------------------------------------------------------------- workflows
async def _knowledge(ticket: dict, analysis: dict, text: str) -> dict:
    rag = await get_rag().answer(text)
    analysis["confidence"] = round(min(analysis["confidence"], rag["confidence"]) if not rag["grounded"] else
                                   0.4 * analysis["confidence"] + 0.6 * rag["confidence"], 3)
    if rag["grounded"] and rag["confidence"] >= get_settings().confidence_threshold:
        t = await update_ticket(ticket["ticket_id"], {"status": "resolved", "resolved_by": "ai", "rag": rag, "analysis": analysis},
                                "answered", f"Grounded answer from {', '.join(s['article_id'] for s in rag['sources'])}")
        await audit("rag.answer", ticket_id=ticket["ticket_id"], details={"sources": [s["article_id"] for s in rag["sources"]], "confidence": rag["confidence"], "generation": rag["generation"]})
        return {"ticket": t, "reply": rag["answer"], "actions": [{"type": "create_ticket", "label": "This didn't help - create a ticket"}]}

    # Not enough approved knowledge: refuse to guess, record a knowledge gap, offer escalation
    analysis.update(category=GENERAL["category"], subcategory=GENERAL["subcategory"], assignment_group=GENERAL["assignment_group"],
                    suggested_resolution=GENERAL["resolution"], kb_article=None)
    t = await update_ticket(ticket["ticket_id"], {"status": "awaiting_user", "rag": rag, "analysis": analysis},
                            "no_answer", "Approved knowledge insufficient - no answer generated")
    await get_db()[KNOWLEDGE_GAPS].insert_one({
        "gap_id": uuid.uuid4().hex[:10], "question": text, "ticket_id": ticket["ticket_id"], "top_score": rag["retrieval_score"],
        "status": "open", "created_at": utcnow(),
    })
    await audit("rag.no_answer", ticket_id=ticket["ticket_id"], status="warning", details={"top_score": rag["retrieval_score"], "threshold": get_settings().rag_min_score})
    return {"ticket": t, "reply": rag["answer"], "actions": [{"type": "create_ticket", "label": "Create a ServiceNow ticket"}]}


async def _incident(ticket: dict, user: dict, analysis: dict, text: str, escalation_reason: str | None = None) -> dict:
    settings = get_settings()
    sn = get_servicenow()
    if analysis["intent"] == "automatable":
        escalation_reason = escalation_reason or f"automation confidence {analysis['confidence']:.2f} below threshold"
        analysis["intent"], analysis["route"] = "incident", ROUTES["incident"]

    # Knowledge-driven suggested resolution
    rag = await get_rag().answer(text) if analysis["category"] != "General" else None
    if rag and rag["grounded"]:
        analysis["suggested_resolution"] = f"{analysis['suggested_resolution']} ({rag['sources'][0]['article_id']}: {rag['sources'][0]['title']})"

    # Non-destructive diagnostics (e.g. VPN gateway / user session check)
    diagnostics = None
    if analysis.get("diagnostic") == "vpn_status_check":
        diagnostics = {"check": "VPN gateway & session status", "result": auto_api.vpn_status(user["user_id"])}
        await audit("automation.vpn_status_check", ticket_id=ticket["ticket_id"], details=diagnostics["result"])

    low_conf = analysis["confidence"] < settings.confidence_threshold
    escalated = low_conf or escalation_reason is not None
    if low_conf:
        escalation_reason = escalation_reason or f"AI confidence {analysis['confidence']:.2f} below threshold {settings.confidence_threshold} - routed to Service Desk for human triage"
        analysis["assignment_group"] = "Service Desk"

    fields = map_incident_fields(analysis, text, user.get("email", user["user_id"]))
    if diagnostics:
        r = diagnostics["result"]
        fields["work_notes"] += f" | Diagnostics: gateway {r['gateway_health']}, last attempt {r['user_last_attempt']} ({r['failure_reason']})"
    if escalated:
        fields["work_notes"] += f" | ESCALATED: {escalation_reason}"
    inc = await sn.create_incident(fields, ticket["ticket_id"])

    t = await update_ticket(ticket["ticket_id"], {
        "type": "incident", "status": "escalated" if escalated else "open", "escalated": escalated,
        "escalation_reason": escalation_reason, "analysis": analysis, "rag": rag, "diagnostics": diagnostics, "servicenow": sn_ref(inc),
    }, "incident_created", f"{inc['number']} -> {analysis['assignment_group']}")

    reply = (f"I've logged incident **{inc['number']}** ({analysis['summary']}) with priority {analysis['priority']}, "
             f"assigned to **{analysis['assignment_group']}**.")
    if escalated:
        reply += " I wasn't confident enough to handle this automatically, so a Service Desk analyst will review it."
    if diagnostics:
        r = diagnostics["result"]
        reply += f"\n\nDiagnostics: the VPN gateway is {r['gateway_health']}; your last attempt failed with `{r['failure_reason']}`."
        if r["failure_reason"] == "password_expired":
            reply += " Your password has expired - ask me to reset it and VPN should work again."
    if rag and rag["grounded"]:
        reply += "\n\nWhile you wait, these approved steps may help:\n\n" + rag["answer"]
    return {"ticket": t, "reply": reply}


async def _service_request(ticket: dict, user: dict, analysis: dict, text: str, software: dict | None) -> dict:
    if software:
        analysis.update(summary=f"Software request: {software['name']}", **{k: v for k, v in find_category("Installation").items() if k in ("category", "subcategory", "assignment_group")})
        await update_ticket(ticket["ticket_id"], {"analysis": analysis})
        sr = await request_software(ticket, user, software, text)
        t = await get_ticket(ticket["ticket_id"])
        if sr["approval_required"]:
            reply = (f"I've raised **{sr['request_number']}** for **{software['name']}**. It's a licensed product, so it needs your "
                     f"line manager's approval first - provisioning starts automatically once approved.")
        else:
            reply = (f"ServiceNow request **{sr['request_number']}** created successfully for **{software['name']} {software['version']}**. "
                     f"It's pre-approved, and provisioning to {user.get('device')} has started (about {software['est_minutes']} minutes).")
        return {"ticket": t, "reply": reply}

    # Not a catalogue item: generic request for review (e.g. access request, unknown software)
    sn = get_servicenow()
    req, _ = await sn.create_request(
        {"short_description": analysis["summary"], "description": text, "requested_for": user.get("email"),
         "assignment_group": analysis["assignment_group"], "approval": "requested", "state": "1"},
        {"short_description": analysis["summary"], "cat_item": "General request", "state": "1"},
        ticket["ticket_id"],
    )
    t = await update_ticket(ticket["ticket_id"], {"status": "awaiting_approval", "servicenow": sn_ref(req)},
                            "service_request", f"{req['number']} created")
    reply = (f"I've created request **{req['number']}** ({analysis['summary']}) and sent it to **{analysis['assignment_group']}** for approval.")
    if analysis["subcategory"] == "Installation":
        reply += " That software isn't in the approved catalogue, so it needs a security and licence review."
    return {"ticket": t, "reply": reply}


async def escalate_ticket(ticket_id: str, note: str | None = None) -> dict:
    """User clicked 'create ticket' (e.g. after an unanswered question) - create a ServiceNow incident."""
    ticket = await get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    if ticket.get("servicenow") and ticket["servicenow"].get("table") == "incident":
        return {"ticket": ticket, "reply": f"Incident {ticket['servicenow']['number']} already exists for this request."}
    user = await get_user(ticket["user_id"])
    analysis = ticket["analysis"]
    analysis.update(intent="incident", route=ROUTES["incident"])
    if analysis["category"] == "General":
        analysis.update(impact="Individual", urgency="Medium", priority="P3")
    reason = note or ("AI could not answer from approved knowledge - escalated at user's request"
                      if not (ticket.get("rag") or {}).get("grounded") else "User reported the AI answer did not resolve the issue")
    fields = map_incident_fields(analysis, ticket["description"], user.get("email", user["user_id"]))
    fields["work_notes"] += f" | ESCALATED: {reason}"
    inc = await get_servicenow().create_incident(fields, ticket_id)
    t = await update_ticket(ticket_id, {"type": "incident", "status": "escalated", "escalated": True, "escalation_reason": reason,
                                        "resolved_by": None, "analysis": analysis, "servicenow": sn_ref(inc)},
                            "escalated", f"{inc['number']} -> {analysis['assignment_group']}")
    await audit("ticket.escalated", actor="user", ticket_id=ticket_id, details={"servicenow": inc["number"], "reason": reason})
    return {"ticket": t, "reply": f"Done - incident **{inc['number']}** has been created and assigned to **{analysis['assignment_group']}**. "
                                  "A helpdesk analyst will follow up with you."}


async def _chat(session_id: str, user_id: str, role: str, content: str, ticket_id: str | None = None) -> None:
    await get_db()[CHAT].insert_one({"session_id": session_id, "user_id": user_id, "role": role, "content": content,
                                     "ticket_id": ticket_id, "timestamp": utcnow()})
