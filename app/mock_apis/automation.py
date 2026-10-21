"""Mock enterprise automation APIs (identity directory, VPN gateway, endpoint management).

In production these calls would go to e.g. Microsoft Graph / Entra ID, the VPN gateway API and
Intune / SCCM / Tanium. Here they simulate realistic state so the self-heal agent can
diagnose, execute and *validate* each action. The same functions are exposed over HTTP by
app.routers.mock_apis so they can be exercised independently (Postman / curl).
"""
import random
import secrets
import uuid
from datetime import timedelta

from app.db import utcnow

# --- simulated identity directory -------------------------------------------------------
_DEFAULT_STATE = {
    "emp001": {"password_expired": True, "locked": False, "privileged": False, "failed_logins": 3, "mfa_registered": True},
    "emp002": {"password_expired": False, "locked": True, "privileged": False, "failed_logins": 5, "mfa_registered": True},
    "adm001": {"password_expired": True, "locked": False, "privileged": True, "failed_logins": 0, "mfa_registered": True},
}
_directory: dict[str, dict] = {}
_endpoints: dict[str, dict] = {}


def reset_state() -> None:
    _directory.clear()
    _endpoints.clear()
    for user, st in _DEFAULT_STATE.items():
        _directory[user] = {**st, "password_last_set": (utcnow() - timedelta(days=93)).isoformat()}


def _user(user_id: str) -> dict:
    if not _directory:
        reset_state()
    return _directory.setdefault(
        user_id,
        {"password_expired": True, "locked": False, "privileged": False, "failed_logins": 2,
         "mfa_registered": True, "password_last_set": (utcnow() - timedelta(days=91)).isoformat()},
    )


def _endpoint(device: str) -> dict:
    return _endpoints.setdefault(
        device,
        {"outlook_cache_mb": 4812, "outlook_sync": "stalled", "spooler": "stopped", "stuck_jobs": 4,
         "teams": "not_responding", "temp_files_mb": 9320, "cpu_pct": 94, "free_disk_pct": 6},
    )


# --- identity ------------------------------------------------------------------------------------
def identity_status(user_id: str) -> dict:
    u = _user(user_id)
    return {"user_id": user_id, **{k: u[k] for k in ("password_expired", "locked", "privileged", "failed_logins", "mfa_registered", "password_last_set")}}


def verify_mfa(user_id: str) -> dict:
    u = _user(user_id)
    return {"user_id": user_id, "method": "authenticator_push", "verified": bool(u["mfa_registered"]), "transaction_id": uuid.uuid4().hex[:10]}


def reset_password(user_id: str) -> dict:
    u = _user(user_id)
    u.update(password_expired=False, locked=False, failed_logins=0, password_last_set=utcnow().isoformat())
    temp = secrets.token_urlsafe(9)
    return {
        "user_id": user_id, "status": "reset", "force_change_at_next_logon": True,
        "temporary_password_delivery": "SMS to registered mobile ******4821",
        "temporary_password_hint": temp[:2] + "*" * 8,  # never return the full secret
    }


def unlock_account(user_id: str) -> dict:
    u = _user(user_id)
    u.update(locked=False, failed_logins=0)
    return {"user_id": user_id, "status": "unlocked"}


# --- network --------------------------------------------------------------------------------------
def vpn_status(user_id: str) -> dict:
    u = _user(user_id)
    return {
        "user_id": user_id,
        "gateway": "vpn-eu-west-1.corp.example.com",
        "gateway_health": "healthy",
        "active_sessions": random.randint(1100, 1400),
        "user_last_attempt": "authentication_failed",
        "failure_reason": "password_expired" if u["password_expired"] else "mfa_token_mismatch",
        "client_version": "GlobalProtect 6.2.1",
        "certificate_valid": True,
    }


# --- endpoint management --------------------------------------------------------------------------
def endpoint_status(device: str) -> dict:
    return {"device": device, **_endpoint(device)}


def clear_outlook_cache(device: str) -> dict:
    e = _endpoint(device)
    freed = e["outlook_cache_mb"]
    e.update(outlook_cache_mb=0, outlook_sync="syncing")
    return {"device": device, "action": "outlook_cache_clear", "freed_mb": freed, "ost_rebuilt": True}


def restart_service(device: str, service: str) -> dict:
    e = _endpoint(device)
    jobs = e["stuck_jobs"]
    e.update(spooler="running", stuck_jobs=0)
    return {"device": device, "service": service, "status": "running", "cleared_jobs": jobs}


def restart_app(device: str, app: str) -> dict:
    e = _endpoint(device)
    e.update(teams="running")
    return {"device": device, "app": app, "status": "running", "pid": random.randint(2000, 9999)}


def cleanup_endpoint(device: str) -> dict:
    e = _endpoint(device)
    freed = e["temp_files_mb"]
    e.update(temp_files_mb=0, cpu_pct=23, free_disk_pct=31)
    return {"device": device, "action": "temp_cleanup", "freed_mb": freed, "restarted_processes": ["SearchIndexer", "OneDrive"]}
