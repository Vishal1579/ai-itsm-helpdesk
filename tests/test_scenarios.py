"""End-to-end tests for the five mandatory demo scenarios plus governance rules."""
import time


def chat(client, message, user_id="emp001"):
    r = client.post("/api/chat", json={"message": message, "user_id": user_id})
    assert r.status_code == 200, r.text
    return r.json()


# 1. Intelligent ticket intake -------------------------------------------------------------
def test_scenario1_vpn_intelligent_ticket(client):
    res = chat(client, "I cannot connect to VPN since this morning. Authentication keeps failing.")
    a = res["ticket"]["analysis"]
    assert res["intent"] == "incident"
    assert (a["category"], a["subcategory"]) == ("Network", "VPN")
    assert a["priority"] == "P2"
    assert (a["impact"], a["urgency"]) == ("Individual", "High")
    assert a["assignment_group"] == "Network Support"
    assert a["summary"] == "VPN authentication failure"
    assert "VPN troubleshooting" in a["suggested_resolution"]

    sn = res["ticket"]["servicenow"]
    assert sn["table"] == "incident" and sn["number"].startswith("INC")
    rec = client.get(f"/api/servicenow/incident/{sn['number']}").json()
    assert rec["short_description"] == "VPN authentication failure"
    assert rec["assignment_group"] == "Network Support"
    assert rec["impact"] == "3" and rec["urgency"] == "1" and rec["priority"].startswith("2")
    # RAG suggested resolution and sources attached
    assert res["ticket"]["rag"]["grounded"]
    assert res["ticket"]["rag"]["sources"][0]["article_id"] == "KB0001"


# 2. Self-heal ----------------------------------------------------------------------------------
def test_scenario2_password_self_heal(client):
    res = chat(client, "My password has expired.")
    t = res["ticket"]
    assert res["intent"] == "automatable"
    assert t["status"] == "resolved" and t["resolved_by"] == "ai"
    steps = [s["step"] for s in t["automation"]["steps"]]
    assert steps == ["Identify", "Diagnose", "Knowledge Search", "Determine Automation", "Execute", "Validate", "Update ServiceNow"]
    assert all(s["status"] in ("success", "warning") for s in t["automation"]["steps"])
    rec = client.get(f"/api/servicenow/incident/{t['servicenow']['number']}").json()
    assert rec["state"] == "6" and rec["close_code"] == "Solved (Automated)"
    # every automated action is in the audit log
    actions = {a["action"] for a in client.get("/api/audit", params={"ticket_id": t["ticket_id"]}).json()}
    assert "automation.password_reset.execute" in actions and "servicenow.incident.update" in actions
    # target system really changed
    assert client.get("/mock/automation/identity/emp001").json()["password_expired"] is False


def test_self_heal_blocked_for_privileged_account(client):
    res = chat(client, "My password has expired.", user_id="adm001")
    t = res["ticket"]
    assert t["status"] == "escalated" and t["escalated"]
    gate = next(s for s in t["automation"]["steps"] if s["step"] == "Determine Automation")
    assert gate["status"] == "blocked" and "privileged" in gate["detail"]
    assert client.get("/mock/automation/identity/adm001").json()["password_expired"] is True


# 3. RAG ----------------------------------------------------------------------------------------
def test_scenario3_rag_outlook(client):
    res = chat(client, "How do I troubleshoot Outlook synchronization?")
    rag = res["ticket"]["rag"]
    assert res["intent"] == "knowledge_question"
    assert rag["grounded"] and rag["sources"][0]["article_id"] == "KB0004"
    assert "[KB0004]" in rag["answer"]
    assert res["ticket"]["resolved_by"] == "ai"


def test_semantic_search_ranks_relevant_article(client):
    r = client.get("/api/kb/search", params={"q": "wireless network keeps dropping"}).json()
    assert r["results"][0]["article_id"] == "KB0005"


# 4. Software provisioning ----------------------------------------------------------------
def test_scenario4_software_provisioning(client):
    res = chat(client, "I need Visual Studio Code installed on my laptop.")
    sr = res["ticket"]["software_request"]
    assert res["intent"] == "service_request"
    assert sr["software"] == "Visual Studio Code"
    assert sr["request_number"].startswith("REQ") and sr["status"] == "Provisioning"
    assert "created successfully" in res["reply"]
    for _ in range(60):
        status = client.get(f"/api/requests/{sr['request_number']}").json()
        if status["status"] == "Completed":
            break
        time.sleep(0.05)
    assert status["status"] == "Completed" and status["progress"] == 100
    req = client.get("/api/servicenow/sc_request").json()[0]
    assert req["number"] == sr["request_number"] and req["state"] == "3"


def test_licensed_software_requires_approval(client):
    res = chat(client, "Please install Adobe Acrobat Pro for me")
    sr = res["ticket"]["software_request"]
    assert sr["status"] == "Awaiting Approval"
    approved = client.post(f"/api/requests/{sr['request_number']}/approve", json={"approved": True}).json()
    assert approved["status"] == "Provisioning"


# 5. Unknown question ------------------------------------------------------------------------
def test_scenario5_unknown_question_no_hallucination(client):
    res = chat(client, "What is the cafeteria menu for Friday?")
    t = res["ticket"]
    assert t["rag"]["grounded"] is False and t["rag"]["sources"] == []
    assert "could not find" in res["reply"].lower()
    assert any(a["type"] == "create_ticket" for a in res["actions"])
    assert client.get("/api/kb/gaps").json()[0]["question"].startswith("What is the cafeteria")
    esc = client.post(f"/api/tickets/{t['ticket_id']}/escalate").json()
    assert esc["ticket"]["escalated"] and esc["ticket"]["servicenow"]["number"].startswith("INC")
    assert esc["ticket"]["analysis"]["assignment_group"] == "Service Desk"


# Governance & integration ------------------------------------------------------------------
def test_low_confidence_is_escalated_to_human(client):
    res = chat(client, "something is weird with my thing")
    t = res["ticket"]
    assert t["analysis"]["confidence"] < t["analysis"]["threshold"]
    assert t["escalated"] and t["analysis"]["assignment_group"] == "Service Desk"


def test_update_incident_syncs_servicenow(client):
    res = chat(client, "My VPN is not connecting.")
    tid = res["ticket"]["ticket_id"]
    upd = client.patch(f"/api/tickets/{tid}", json={"status": "resolved", "work_note": "Reissued VPN certificate"}).json()
    assert upd["status"] == "resolved" and upd["resolved_by"] == "human"
    rec = client.get(f"/api/servicenow/incident/{upd['servicenow']['number']}").json()
    assert rec["state"] == "6"


def test_mock_servicenow_table_api_shape(client):
    created = client.post("/mock/servicenow/api/now/table/incident", json={"short_description": "Test", "impact": "2", "urgency": "2"}).json()
    sys_id = created["result"]["sys_id"]
    got = client.get(f"/mock/servicenow/api/now/table/incident/{sys_id}").json()["result"]
    assert got["number"].startswith("INC") and got["priority"].startswith("2")


def test_knowledge_article_publish_is_searchable(client):
    body = {"title": "Docking Station Troubleshooting", "category": "Hardware", "subcategory": "Docking Station",
            "content": "## Monitor not detected\n1. Unplug the USB-C dock cable and reconnect it.\n2. Update the dock firmware from the Company Portal."}
    art = client.post("/api/kb/articles", json=body).json()["article"]
    hits = client.get("/api/kb/search", params={"q": "external monitor not detected on dock"}).json()["results"]
    assert hits[0]["article_id"] == art["article_id"]


def test_dashboard_counts(client):
    chat(client, "My password has expired.")
    chat(client, "What is the cafeteria menu for Friday?")
    stats = client.get("/api/dashboard/stats").json()["totals"]
    assert stats["total"] == 2 and stats["ai_resolved"] == 1 and stats["automation_runs"] == 1
