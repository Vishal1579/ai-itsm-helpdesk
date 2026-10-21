import os
import tempfile

# Deterministic, offline-friendly test configuration (must be set before the app is imported)
# DB_MODE can be overridden, e.g. DB_MODE=mongodb MONGODB_URI=... pytest, to run against a real MongoDB
os.environ.setdefault("DB_MODE", "memory")
os.environ.setdefault("MONGODB_DB", "itsm_helpdesk_test")
os.environ.update(
    LLM_PROVIDER="extractive",
    SERVICENOW_MODE="mock",
    PROVISIONING_STEP_SECONDS="0.05",
    VECTOR_STORE_DIR=tempfile.mkdtemp(prefix="itsm-vs-"),
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset(client):
    client.post("/api/admin/reset-demo")
    yield
