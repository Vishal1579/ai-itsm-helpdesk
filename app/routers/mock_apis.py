"""HTTP faces of the mock systems, so they can be inspected / called like the real ones.

/mock/servicenow/api/now/table/{table}  - ServiceNow Table API shape ({"result": ...})
/mock/automation/...                     - identity, VPN and endpoint management mock APIs
/mock/provisioning/jobs/{job_id}         - software provisioning job status
"""
from fastapi import APIRouter, Body, HTTPException

from app.integrations.servicenow import MockServiceNowClient
from app.mock_apis import automation as api
from app.mock_apis import catalog as prov

router = APIRouter(prefix="/mock", tags=["mock systems"])
_sn = MockServiceNowClient()


@router.get("/servicenow/api/now/table/{table}")
async def sn_list(table: str, sysparm_limit: int = 50):
    return {"result": await _sn.list_records(table, sysparm_limit)}


@router.get("/servicenow/api/now/table/{table}/{sys_id}")
async def sn_get(table: str, sys_id: str):
    rec = await _sn.get_record(table, sys_id)
    if not rec:
        raise HTTPException(404, {"error": {"message": "No Record found"}, "status": "failure"})
    return {"result": rec}


@router.post("/servicenow/api/now/table/{table}", status_code=201)
async def sn_create(table: str, fields: dict = Body(...)):
    return {"result": await _sn.create_record(table, fields)}


@router.patch("/servicenow/api/now/table/{table}/{sys_id}")
async def sn_update(table: str, sys_id: str, fields: dict = Body(...)):
    if not await _sn.get_record(table, sys_id):
        raise HTTPException(404, {"error": {"message": "No Record found"}, "status": "failure"})
    return {"result": await _sn.update_record(table, sys_id, fields)}


@router.get("/automation/identity/{user_id}")
async def identity_status(user_id: str):
    return api.identity_status(user_id)


@router.post("/automation/identity/{user_id}/reset-password")
async def reset_password(user_id: str):
    return api.reset_password(user_id)


@router.post("/automation/identity/{user_id}/unlock")
async def unlock(user_id: str):
    return api.unlock_account(user_id)


@router.get("/automation/vpn/{user_id}")
async def vpn(user_id: str):
    return api.vpn_status(user_id)


@router.get("/automation/endpoint/{device}")
async def endpoint(device: str):
    return api.endpoint_status(device)


@router.post("/automation/reset")
async def reset_mock_state():
    api.reset_state()
    return {"status": "mock systems reset to demo state"}


@router.get("/provisioning/jobs/{job_id}")
async def job(job_id: str):
    j = prov.get_job(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return j
