"""Approved Software Catalogue (seeded into MongoDB) and mock provisioning API (Intune/SCCM style)."""
import re
import uuid

from app.db import utcnow

SOFTWARE_CATALOG = [
    {"sku": "SW-VSCODE", "name": "Visual Studio Code", "aliases": ["vs code", "vscode", "visual studio code"], "vendor": "Microsoft", "version": "1.105", "category": "Developer Tools", "license": "free", "approval_required": False, "est_minutes": 10},
    {"sku": "SW-CHROME", "name": "Google Chrome", "aliases": ["chrome", "google chrome"], "vendor": "Google", "version": "141", "category": "Browsers", "license": "free", "approval_required": False, "est_minutes": 5},
    {"sku": "SW-ZOOM", "name": "Zoom Workplace", "aliases": ["zoom"], "vendor": "Zoom", "version": "6.5", "category": "Collaboration", "license": "free", "approval_required": False, "est_minutes": 5},
    {"sku": "SW-SLACK", "name": "Slack", "aliases": ["slack"], "vendor": "Salesforce", "version": "4.46", "category": "Collaboration", "license": "free", "approval_required": False, "est_minutes": 5},
    {"sku": "SW-GIT", "name": "Git for Windows", "aliases": ["git"], "vendor": "Git SCM", "version": "2.51", "category": "Developer Tools", "license": "free", "approval_required": False, "est_minutes": 5},
    {"sku": "SW-POSTMAN", "name": "Postman", "aliases": ["postman"], "vendor": "Postman", "version": "11.6", "category": "Developer Tools", "license": "free", "approval_required": False, "est_minutes": 5},
    {"sku": "SW-7ZIP", "name": "7-Zip", "aliases": ["7-zip", "7zip"], "vendor": "Igor Pavlov", "version": "25.01", "category": "Utilities", "license": "free", "approval_required": False, "est_minutes": 3},
    {"sku": "SW-PYTHON", "name": "Python 3.13", "aliases": ["python"], "vendor": "PSF", "version": "3.13", "category": "Developer Tools", "license": "free", "approval_required": False, "est_minutes": 8},
    {"sku": "SW-DOCKER", "name": "Docker Desktop", "aliases": ["docker desktop", "docker"], "vendor": "Docker", "version": "4.47", "category": "Developer Tools", "license": "licensed", "approval_required": True, "est_minutes": 15},
    {"sku": "SW-ACROBAT", "name": "Adobe Acrobat Pro", "aliases": ["adobe acrobat", "acrobat", "adobe pro"], "vendor": "Adobe", "version": "2025", "category": "Productivity", "license": "licensed", "approval_required": True, "est_minutes": 15},
    {"sku": "SW-VISIO", "name": "Microsoft Visio", "aliases": ["visio"], "vendor": "Microsoft", "version": "2024", "category": "Productivity", "license": "licensed", "approval_required": True, "est_minutes": 15},
    {"sku": "SW-INTELLIJ", "name": "IntelliJ IDEA Ultimate", "aliases": ["intellij", "idea ultimate"], "vendor": "JetBrains", "version": "2025.2", "category": "Developer Tools", "license": "licensed", "approval_required": True, "est_minutes": 15},
]


def match_software(text: str, catalog: list[dict] | None = None) -> dict | None:
    """Longest alias match wins, so 'visual studio code' beats 'code'."""
    text_l = text.lower()
    best, best_len = None, 0
    for item in catalog or SOFTWARE_CATALOG:
        for alias in [item["name"].lower(), *item["aliases"]]:
            if len(alias) > best_len and re.search(rf"\b{re.escape(alias)}\b", text_l):
                best, best_len = item, len(alias)
    return best


def catalog_terms(catalog: list[dict] | None = None) -> list[str]:
    terms = []
    for item in catalog or SOFTWARE_CATALOG:
        terms += [item["name"], *item["aliases"]]
    return terms


# --- mock provisioning API (in-memory job store) ---------------------------------------------
_jobs: dict[str, dict] = {}


def create_provisioning_job(sku: str, device: str, user_id: str) -> dict:
    job = {"job_id": f"PRV-{uuid.uuid4().hex[:8].upper()}", "sku": sku, "device": device, "user_id": user_id,
           "status": "queued", "created_at": utcnow().isoformat(), "progress": 0}
    _jobs[job["job_id"]] = job
    return dict(job)


def update_job(job_id: str, status: str, progress: int) -> dict:
    job = _jobs[job_id]
    job.update(status=status, progress=progress, updated_at=utcnow().isoformat())
    return dict(job)


def get_job(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    return dict(job) if job else None
