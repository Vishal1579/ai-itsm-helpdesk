"""Seed reference data (users, software catalogue). Knowledge articles are synced from knowledge_base/."""
from app.db import SOFTWARE_CATALOG, USERS, get_db
from app.mock_apis.catalog import SOFTWARE_CATALOG as CATALOG
from app.tickets import DEMO_USERS


async def seed() -> None:
    db = get_db()
    for u in DEMO_USERS:
        await db[USERS].update_one({"user_id": u["user_id"]}, {"$set": u}, upsert=True)
    for item in CATALOG:
        await db[SOFTWARE_CATALOG].update_one({"sku": item["sku"]}, {"$set": item}, upsert=True)
