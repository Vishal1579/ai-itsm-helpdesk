"""Software provisioning automation.

Employee -> AI intent detection -> Software Catalogue -> ServiceNow Request (REQ + RITM)
         -> [manager approval for licensed software] -> Mock Provisioning API -> status updates.
"""
import asyncio
import logging

from app.audit import audit
from app.config import get_settings
from app.db import SOFTWARE_REQUESTS, clean, get_db, utcnow
from app.integrations.servicenow import get_servicenow
from app.mock_apis import catalog as prov_api
from app.tickets import sn_ref, update_ticket

log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()

STATUS_SUBMITTED = "Submitted"
STATUS_AWAITING = "Awaiting Approval"
STATUS_APPROVED = "Approved"
STATUS_PROVISIONING = "Provisioning"
STATUS_COMPLETED = "Completed"
STATUS_REJECTED = "Rejected"


async def request_software(ticket: dict, user: dict, item: dict, description: str) -> dict:
    sn = get_servicenow()
    req, ritm = await sn.create_request(
        {
            "short_description": f"Software request: {item['name']}",
            "description": description,
            "requested_for": user.get("email", user["user_id"]),
            "opened_by": "ai.helpdesk.integration",
            "approval": "requested" if item["approval_required"] else "approved",
            "assignment_group": "Software Distribution",
            "u_ai_intent": "service_request",
            "state": "1",
        },
        {
            "short_description": f"Install {item['name']} {item['version']} on {user.get('device')}",
            "cat_item": item["name"],
            "u_sku": item["sku"],
            "quantity": "1",
            "stage": "waiting_for_approval" if item["approval_required"] else "request_approved",
            "state": "1",
        },
        ticket["ticket_id"],
    )
    now = utcnow()
    status = STATUS_AWAITING if item["approval_required"] else STATUS_APPROVED
    doc = {
        "request_number": req["number"],
        "ritm_number": ritm["number"],
        "sys_id": req["sys_id"],
        "ritm_sys_id": ritm["sys_id"],
        "ticket_id": ticket["ticket_id"],
        "user_id": user["user_id"],
        "user_name": user.get("name"),
        "device": user.get("device"),
        "software": item["name"],
        "sku": item["sku"],
        "version": item["version"],
        "license": item["license"],
        "approval_required": item["approval_required"],
        "status": status,
        "progress": 0,
        "job_id": None,
        "history": [
            {"at": now, "status": STATUS_SUBMITTED, "note": f"ServiceNow {req['number']} / {ritm['number']} created"},
            {"at": now, "status": status, "note": "Licensed software - waiting for line-manager approval" if item["approval_required"] else "Pre-approved catalogue item (free licence)"},
        ],
        "created_at": now,
        "updated_at": now,
    }
    await get_db()[SOFTWARE_REQUESTS].insert_one(dict(doc))
    await audit("provisioning.request.created", ticket_id=ticket["ticket_id"], details={"request": req["number"], "software": item["name"], "approval_required": item["approval_required"]})

    if not item["approval_required"]:
        doc = await start_provisioning(doc["request_number"])
    await update_ticket(ticket["ticket_id"], {"status": "awaiting_approval" if item["approval_required"] else "provisioning",
                                              "servicenow": sn_ref(req), "software_request": _ref(doc)},
                        "service_request", f"{req['number']} created for {item['name']}")
    return clean(doc)


async def approve(request_number: str, approver: str = "line.manager", approved: bool = True) -> dict:
    sr = await _get(request_number)
    if sr["status"] != STATUS_AWAITING:
        return sr
    sn = get_servicenow()
    if not approved:
        await sn.update_request(sr["sys_id"], {"approval": "rejected", "state": "4", "work_notes": f"Rejected by {approver}"}, sr["ticket_id"])
        sr = await _set(request_number, STATUS_REJECTED, f"Rejected by {approver}")
        await update_ticket(sr["ticket_id"], {"status": "closed", "software_request": _ref(sr)}, "rejected", f"Rejected by {approver}")
        return sr
    await sn.update_request(sr["sys_id"], {"approval": "approved", "work_notes": f"Approved by {approver}"}, sr["ticket_id"])
    await sn.update_request_item(sr["ritm_sys_id"], {"stage": "request_approved"})
    await _set(request_number, STATUS_APPROVED, f"Approved by {approver}")
    await audit("provisioning.request.approved", actor=approver, ticket_id=sr["ticket_id"], details={"request": request_number})
    return await start_provisioning(request_number)


async def start_provisioning(request_number: str) -> dict:
    sr = await _get(request_number)
    job = prov_api.create_provisioning_job(sr["sku"], sr["device"], sr["user_id"])
    sn = get_servicenow()
    await sn.update_request(sr["sys_id"], {"state": "2", "work_notes": f"Provisioning job {job['job_id']} submitted to endpoint management"}, sr["ticket_id"])
    await sn.update_request_item(sr["ritm_sys_id"], {"stage": "fulfillment", "state": "2"})
    await get_db()[SOFTWARE_REQUESTS].update_one({"request_number": request_number}, {"$set": {"job_id": job["job_id"]}})
    sr = await _set(request_number, STATUS_PROVISIONING, f"Mock provisioning API accepted job {job['job_id']}", progress=10)
    await audit("provisioning.job.submitted", ticket_id=sr["ticket_id"], details={"request": request_number, "job": job})
    await update_ticket(sr["ticket_id"], {"status": "provisioning", "software_request": _ref(sr)}, "provisioning", job["job_id"])
    task = asyncio.create_task(_progress(request_number, job["job_id"]))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return sr


async def _progress(request_number: str, job_id: str) -> None:
    """Simulate the endpoint-management system pushing the package and reporting back."""
    step = get_settings().provisioning_step_seconds
    try:
        for status, progress in (("downloading", 40), ("installing", 75)):
            await asyncio.sleep(step)
            prov_api.update_job(job_id, status, progress)
            await get_db()[SOFTWARE_REQUESTS].update_one({"request_number": request_number}, {"$set": {"progress": progress, "job_status": status, "updated_at": utcnow()}})
        await asyncio.sleep(step)
        prov_api.update_job(job_id, "succeeded", 100)
        sr = await _set(request_number, STATUS_COMPLETED, f"Job {job_id} succeeded - installed on {(await _get(request_number))['device']}", progress=100)
        sn = get_servicenow()
        await sn.update_request(sr["sys_id"], {"state": "3", "work_notes": f"Software installed by provisioning job {job_id}. Closed Complete."}, sr["ticket_id"])
        await sn.update_request_item(sr["ritm_sys_id"], {"stage": "complete", "state": "3"})
        await audit("provisioning.job.completed", ticket_id=sr["ticket_id"], details={"request": request_number, "job_id": job_id})
        await update_ticket(sr["ticket_id"], {"status": "resolved", "resolved_by": "ai", "software_request": _ref(sr),
                                              "servicenow.state": "3", "servicenow.state_label": "Closed Complete"},
                            "completed", f"{sr['software']} installed")
    except Exception:  # pragma: no cover
        log.exception("Provisioning simulation failed for %s", request_number)


async def _get(request_number: str) -> dict:
    sr = clean(await get_db()[SOFTWARE_REQUESTS].find_one({"request_number": request_number}))
    if not sr:
        raise KeyError(request_number)
    return sr


async def _set(request_number: str, status: str, note: str, progress: int | None = None) -> dict:
    fields = {"status": status, "updated_at": utcnow()}
    if progress is not None:
        fields["progress"] = progress
    await get_db()[SOFTWARE_REQUESTS].update_one(
        {"request_number": request_number}, {"$set": fields, "$push": {"history": {"at": utcnow(), "status": status, "note": note}}}
    )
    return await _get(request_number)


def _ref(sr: dict) -> dict:
    return {k: sr.get(k) for k in ("request_number", "ritm_number", "software", "version", "status", "progress", "approval_required", "job_id")}
