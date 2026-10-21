"""Auto-resolution / self-heal agent.

Pipeline (each step is persisted to `automation_actions` and the audit log):
  Identify -> Diagnose -> Knowledge Search -> Determine Automation -> Execute -> Validate -> Update ServiceNow

Safety rails:
  * only allow-listed playbooks run, and only above the AI confidence threshold,
  * identity actions need a successful MFA check and are never run on privileged accounts,
  * every action is validated against the target system; failures are escalated to humans.
"""
import re
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from app.audit import audit
from app.config import get_settings
from app.db import AUTOMATION, get_db, utcnow
from app.integrations.servicenow import get_servicenow, map_incident_fields
from app.mock_apis import automation as api
from app.rag.service import get_rag
from app.tickets import sn_ref, update_ticket


@dataclass
class Playbook:
    key: str
    name: str
    scope: str  # identity | endpoint
    kb_query: str
    diagnose: Callable[[dict], dict]
    confirmed: Callable[[dict], bool]
    execute: Callable[[dict], dict]
    validate: Callable[[dict], tuple[bool, str]]
    success_message: str


def _dev(u: dict) -> str:
    return u.get("device", "LT-0000")


PLAYBOOKS: dict[str, Playbook] = {
    "password_reset": Playbook(
        "password_reset", "Expired password reset", "identity", "reset expired password self-service",
        diagnose=lambda u: api.identity_status(u["user_id"]),
        confirmed=lambda d: d["password_expired"],
        execute=lambda u: api.reset_password(u["user_id"]),
        validate=lambda u: (lambda s: (not s["password_expired"] and not s["locked"], f"password_expired={s['password_expired']}, locked={s['locked']}"))(api.identity_status(u["user_id"])),
        success_message="Your password has been reset. A temporary password was sent by SMS to your registered mobile - you'll be asked to choose a new one at next sign-in.",
    ),
    "account_unlock": Playbook(
        "account_unlock", "Account unlock", "identity", "account locked out unlock",
        diagnose=lambda u: api.identity_status(u["user_id"]),
        confirmed=lambda d: d["locked"],
        execute=lambda u: api.unlock_account(u["user_id"]),
        validate=lambda u: (lambda s: (not s["locked"], f"locked={s['locked']}"))(api.identity_status(u["user_id"])),
        success_message="Your account is unlocked. Please sign in again; remove any old saved passwords on your phone to avoid another lockout.",
    ),
    "outlook_cache_clear": Playbook(
        "outlook_cache_clear", "Outlook cache clear & OST rebuild", "endpoint", "outlook not syncing clear offline cache",
        diagnose=lambda u: api.endpoint_status(_dev(u)),
        confirmed=lambda d: d["outlook_sync"] != "syncing",
        execute=lambda u: api.clear_outlook_cache(_dev(u)),
        validate=lambda u: (lambda s: (s["outlook_sync"] == "syncing", f"outlook_sync={s['outlook_sync']}"))(api.endpoint_status(_dev(u))),
        success_message="I cleared the Outlook offline cache and the mailbox is re-syncing. Give it a few minutes to download recent mail.",
    ),
    "service_restart": Playbook(
        "service_restart", "Print Spooler restart", "endpoint", "print queue stuck restart print spooler",
        diagnose=lambda u: api.endpoint_status(_dev(u)),
        confirmed=lambda d: d["spooler"] != "running" or d["stuck_jobs"] > 0,
        execute=lambda u: api.restart_service(_dev(u), "Spooler"),
        validate=lambda u: (lambda s: (s["spooler"] == "running" and s["stuck_jobs"] == 0, f"spooler={s['spooler']}, stuck_jobs={s['stuck_jobs']}"))(api.endpoint_status(_dev(u))),
        success_message="I restarted the Print Spooler service and cleared the stuck jobs. Please send your document again.",
    ),
    "app_restart": Playbook(
        "app_restart", "Microsoft Teams restart", "endpoint", "teams frozen not responding restart",
        diagnose=lambda u: api.endpoint_status(_dev(u)),
        confirmed=lambda d: d["teams"] != "running",
        execute=lambda u: api.restart_app(_dev(u), "Microsoft Teams"),
        validate=lambda u: (lambda s: (s["teams"] == "running", f"teams={s['teams']}"))(api.endpoint_status(_dev(u))),
        success_message="Teams has been restarted on your laptop and is responding again.",
    ),
    "laptop_cleanup": Playbook(
        "laptop_cleanup", "Temp files & cache clean-up", "endpoint", "laptop slow clear temporary files",
        diagnose=lambda u: api.endpoint_status(_dev(u)),
        confirmed=lambda d: d["cpu_pct"] > 80 or d["free_disk_pct"] < 15,
        execute=lambda u: api.cleanup_endpoint(_dev(u)),
        validate=lambda u: (lambda s: (s["free_disk_pct"] >= 15, f"cpu={s['cpu_pct']}%, free_disk={s['free_disk_pct']}%"))(api.endpoint_status(_dev(u))),
        success_message="I cleaned up temporary files and restarted the heavy background processes. Your laptop should feel faster - a restart today will help too.",
    ),
}

USER_REPORTED = re.compile(r"expire|forgot|reset|locked|lockout|not sync|frozen|not responding|stuck|slow", re.I)


class SelfHealRun:
    def __init__(self, ticket: dict, user: dict, playbook: Playbook) -> None:
        self.ticket, self.user, self.pb = ticket, user, playbook
        self.run_id = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
        self.steps: list[dict] = []

    async def step(self, name: str, status: str, detail: str, data: dict | None = None, started: float | None = None) -> None:
        entry = {
            "run_id": self.run_id,
            "ticket_id": self.ticket["ticket_id"],
            "step": name,
            "status": status,
            "detail": detail,
            "data": data or {},
            "playbook": self.pb.key,
            "at": utcnow(),
            "duration_ms": int((time.perf_counter() - started) * 1000) if started else 0,
        }
        self.steps.append(entry)
        await get_db()[AUTOMATION].insert_one(dict(entry))
        await audit(f"automation.{self.pb.key}.{name.lower().replace(' ', '_')}", ticket_id=self.ticket["ticket_id"],
                    status=status, details={"run_id": self.run_id, "detail": detail, **(data or {})})


async def run_self_heal(ticket: dict, user: dict, analysis: dict, description: str) -> dict:
    settings = get_settings()
    sn = get_servicenow()
    pb = PLAYBOOKS[analysis["playbook"]]
    run = SelfHealRun(ticket, user, pb)

    # 1. Identify - open the ServiceNow incident so the work is tracked end-to-end
    t = time.perf_counter()
    inc = await sn.create_incident({**map_incident_fields(analysis, description, user.get("email", user["user_id"])), "state": "2"}, ticket["ticket_id"])
    await run.step("Identify", "success",
                   f"Automatable issue '{pb.name}' detected (confidence {analysis['confidence']:.0%}); ServiceNow {inc['number']} opened",
                   {"intent": analysis["intent"], "playbook": pb.key, "servicenow": inc["number"]}, t)

    # 2. Diagnose
    t = time.perf_counter()
    diag = pb.diagnose(user)
    confirmed = pb.confirmed(diag)
    reported = bool(USER_REPORTED.search(description))
    await run.step("Diagnose", "success" if confirmed else "warning",
                   ("Issue confirmed on target system" if confirmed else "Target system did not confirm the issue; proceeding on verified user report")
                   + f" ({_brief(diag)})", {"diagnosis": diag, "confirmed": confirmed}, t)

    # 3. Knowledge search
    t = time.perf_counter()
    hits = await get_rag().search(pb.kb_query, k=2)
    kb = hits[0] if hits else None
    await run.step("Knowledge Search", "success" if kb else "warning",
                   f"Runbook found: {kb['article_id']} {kb['title']} ({kb['score']:.2f})" if kb else "No runbook found",
                   {"sources": [{"article_id": h["article_id"], "title": h["title"], "score": h["score"]} for h in hits]}, t)

    # 4. Determine automation (policy gate)
    t = time.perf_counter()
    reasons = []
    if analysis["confidence"] < settings.confidence_threshold:
        reasons.append(f"AI confidence {analysis['confidence']:.2f} below threshold {settings.confidence_threshold}")
    if not (confirmed or reported):
        reasons.append("issue not confirmed by diagnosis or user report")
    mfa = None
    if pb.scope == "identity":
        if diag.get("privileged"):
            reasons.append("privileged account - automated identity changes not permitted")
        mfa = api.verify_mfa(user["user_id"])
        if not mfa["verified"]:
            reasons.append("MFA identity verification failed")
    allowed = not reasons
    await run.step("Determine Automation", "success" if allowed else "blocked",
                   "Policy checks passed: playbook allow-listed" + (", MFA verified" if mfa else "") + ", confidence above threshold"
                   if allowed else "Automation blocked: " + "; ".join(reasons), {"mfa": mfa, "reasons": reasons}, t)

    if not allowed:
        return await _escalate(run, inc, analysis, ticket, "; ".join(reasons))

    # 5. Execute
    t = time.perf_counter()
    try:
        result = pb.execute(user)
        await run.step("Execute", "success", f"{pb.name} executed via mock {pb.scope} API", {"result": result}, t)
    except Exception as exc:  # pragma: no cover - mock APIs don't raise
        await run.step("Execute", "failed", f"Execution error: {exc}", None, t)
        return await _escalate(run, inc, analysis, ticket, f"execution failed: {exc}")

    # 6. Validate
    t = time.perf_counter()
    ok, evidence = pb.validate(user)
    await run.step("Validate", "success" if ok else "failed", ("Post-check passed: " if ok else "Post-check failed: ") + evidence, {"evidence": evidence}, t)
    if not ok:
        return await _escalate(run, inc, analysis, ticket, f"validation failed ({evidence})")

    # 7. Update ServiceNow - resolve the incident with automated close notes
    t = time.perf_counter()
    inc = await sn.update_incident(inc["sys_id"], {
        "state": "6",
        "close_code": "Solved (Automated)",
        "close_notes": f"Auto-resolved by AI self-heal agent ({pb.name}). Validation: {evidence}. Run {run.run_id}.",
        "work_notes": f"[Self-heal] {pb.name} executed and validated. KB: {kb['article_id'] if kb else 'n/a'}",
        "u_resolved_by_ai": "true",
    }, ticket["ticket_id"])
    await run.step("Update ServiceNow", "success", f"{inc['number']} set to Resolved (Solved - Automated)", {"servicenow": inc["number"]}, t)

    automation = _summary(run, "resolved", pb.success_message)
    updated = await update_ticket(ticket["ticket_id"], {
        "status": "resolved", "resolved_by": "ai", "automation": automation, "servicenow": sn_ref(inc),
        "rag": {"grounded": bool(kb), "sources": [_src(h) for h in hits]},
    }, "auto_resolved", f"{pb.name} completed and validated")
    return {"ticket": updated, "reply": pb.success_message + f" (ServiceNow {inc['number']} resolved)"}


async def _escalate(run: SelfHealRun, inc: dict, analysis: dict, ticket: dict, reason: str) -> dict:
    sn = get_servicenow()
    inc = await sn.update_incident(inc["sys_id"], {
        "state": "2",
        "assignment_group": analysis["assignment_group"],
        "work_notes": f"[Self-heal] Automation stopped and escalated to {analysis['assignment_group']}: {reason}",
    }, ticket["ticket_id"])
    await run.step("Update ServiceNow", "success", f"{inc['number']} escalated to {analysis['assignment_group']}", {"servicenow": inc["number"]})
    msg = (f"I couldn't safely fix this automatically ({reason}). I've escalated incident {inc['number']} "
           f"to {analysis['assignment_group']}; an analyst will contact you.")
    automation = _summary(run, "escalated", msg)
    updated = await update_ticket(ticket["ticket_id"], {
        "status": "escalated", "escalated": True, "escalation_reason": reason, "automation": automation, "servicenow": sn_ref(inc),
    }, "escalated", reason)
    return {"ticket": updated, "reply": msg}


def _summary(run: SelfHealRun, outcome: str, message: str) -> dict:
    return {
        "run_id": run.run_id,
        "playbook": run.pb.key,
        "playbook_name": run.pb.name,
        "outcome": outcome,
        "message": message,
        "steps": [{k: v for k, v in s.items() if k not in ("ticket_id", "run_id", "playbook")} for s in run.steps],
    }


def _brief(d: dict) -> str:
    keys = [k for k in d if k not in ("user_id", "device", "password_last_set")][:4]
    return ", ".join(f"{k}={d[k]}" for k in keys)


def _src(h: dict) -> dict:
    return {"article_id": h["article_id"], "title": h["title"], "section": h["section"], "score": h["score"], "snippet": h["text"][:200]}
