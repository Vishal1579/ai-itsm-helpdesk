# AI-Powered ITSM Helpdesk

Prototype of an enterprise IT helpdesk (React portal + FastAPI backend) that understands employee requests, answers from an approved knowledge base, fixes common issues automatically, provisions software and records everything in ServiceNow.

The repository holds both halves: the backend at the root and the React employee portal in [`frontend/`](frontend/).

| Capability | What it does here |
|---|---|
| 1. Intelligent ticket intake | Classifies intent, category and sub-category, impact, urgency, priority, assignment group, summary and suggested resolution, then creates the ServiceNow incident |
| 2. Auto resolution / self-heal | Runs Identify → Diagnose → Knowledge Search → Determine Automation → Execute → Validate → Update ServiceNow through mock identity and endpoint APIs, with a full audit log |
| 3. Knowledge management | Document → chunking → embeddings → FAISS → semantic search → LLM → grounded answer with sources. Articles can be published from the portal, drafted from tickets, and unanswered questions are tracked as knowledge gaps |
| 4. Self-service portal & chatbot | Routes each message to *Knowledge Question*, *Incident*, *Service Request* or *Automatable Issue* |
| 5. Software provisioning | Intent → software catalogue → ServiceNow REQ/RITM → manager approval for licensed items → mock provisioning API → live status |

---

## Architecture

```
React portal (frontend/, Vite :5173)
        │  /api/*  (proxied)
        ▼
FastAPI (this repo, :8000)
  ├── orchestrator.py ── routes each request ──┬── RAG service ── FAISS + sentence-transformers ── Hugging Face LLM
  │                                            ├── self-heal agent ── mock identity / VPN / endpoint APIs
  │                                            ├── provisioning agent ── catalogue + mock provisioning API
  │                                            └── incident workflow
  ├── ai/classifier.py  hybrid rules + embedding few-shot triage, ITIL priority matrix
  ├── integrations/servicenow.py  Live Table API client | Mock client (same interface)
  └── audit.py  every AI decision, automated action and ServiceNow call
        │
        ▼
MongoDB Atlas: tickets, users, knowledge_articles, knowledge_chunks, knowledge_gaps, chat_history,
               automation_actions, software_requests, software_catalog, audit_logs, servicenow_mock_records
```

End-to-end journey: **employee request → AI understanding → knowledge retrieval → intelligent decision → automation → ServiceNow → resolution**, with human escalation whenever confidence is low or an action is unsafe.

### Repository layout

```
frontend/                 React + TypeScript employee portal (see frontend/README.md)
app/
  main.py                 FastAPI app, start-up (DB, seed, index build, LLM warm-up)
  config.py               all settings (env / .env)
  db.py                   Motor client, collections, in-memory fallback
  orchestrator.py         intent routing and the four workflows
  tickets.py              local ticket store
  audit.py                audit log writer
  seed.py                 demo users and software catalogue
  ai/classifier.py        intake classification and confidence
  ai/taxonomy.py          categories, assignment groups, playbooks, exemplars, priority matrix
  ai/embeddings.py        sentence-transformers wrapper (+ hashing fallback)
  ai/llm.py               Hugging Face LLM: local transformers | Inference API | extractive
  rag/chunking.py         markdown parsing and heading-aware chunking
  rag/vector_store.py     FAISS index persisted to data/vector_store
  rag/service.py          retrieval, re-ranking, grounded generation, faithfulness guard
  agents/self_heal.py     7-step self-heal pipeline and safety gates
  agents/provisioning.py  REQ/RITM, approval, provisioning job progression
  integrations/servicenow.py  live + mock ServiceNow clients, field mapping
  mock_apis/automation.py mock identity directory, VPN gateway, endpoint management
  mock_apis/catalog.py    software catalogue and mock provisioning API
  routers/api.py          public REST API
  routers/mock_apis.py    HTTP faces of the mock systems (ServiceNow Table API shape)
knowledge_base/           10 sample IT knowledge articles (markdown + front matter)
tests/                    end-to-end scenario tests
```

---

## Setup

Prerequisites: Python 3.11+ (built with 3.13), Node 20+ for the frontend, and optionally a MongoDB Atlas cluster.

```bash
cd itsm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in MONGODB_URI etc.
uvicorn app.main:app --reload --port 8000
```

The first start downloads `all-MiniLM-L6-v2` (~90 MB) and `Qwen2.5-0.5B-Instruct` (~1 GB) from Hugging Face and builds the FAISS index. Later starts reuse both.

Then, in a second terminal from the repository root, start the portal:

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Interactive API docs: http://localhost:8000/docs

### MongoDB Atlas

1. Create a free M0 cluster, a database user and a network access rule for your IP.
2. Copy the `mongodb+srv://` connection string into `MONGODB_URI` in `.env`.
3. Collections and indexes are created on start-up. Knowledge articles, demo users and the software catalogue are seeded automatically.

With `DB_MODE=auto` (the default), the backend falls back to an in-memory MongoDB if the cluster can't be reached, so a demo never fails on venue Wi-Fi. `GET /api/health` and the portal sidebar show which one is active. Set `DB_MODE=mongodb` to make a connection failure fatal instead.

### Configuration

All settings are environment variables (see [.env.example](.env.example)). Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `MONGODB_URI` / `MONGODB_DB` | `mongodb://localhost:27017` / `itsm_helpdesk` | Atlas connection |
| `DB_MODE` | `auto` | `auto`, `mongodb` or `memory` |
| `LLM_PROVIDER` | `local` | `local`, `hf_inference` or `extractive` |
| `LLM_LOCAL_MODEL` | `Qwen/Qwen2.5-0.5B-Instruct` | model for local generation |
| `LLM_HF_MODEL` / `HF_TOKEN` | `Qwen/Qwen2.5-7B-Instruct` | Hugging Face Inference Providers |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | embeddings |
| `RAG_MIN_SCORE` | `0.45` | minimum cosine similarity for a passage to be used |
| `CONFIDENCE_THRESHOLD` | `0.60` | below this the request goes to a person |
| `SERVICENOW_MODE` | `mock` | `mock` or `live` |
| `SERVICENOW_INSTANCE` / `_USER` / `_PASSWORD` | none | live ServiceNow instance |
| `PROVISIONING_STEP_SECONDS` | `6` | speed of the simulated provisioning job |

---

## AI design

### Model choice

| Role | Model | Why |
|---|---|---|
| Answer generation (default) | **Qwen/Qwen2.5-0.5B-Instruct** run locally with `transformers` | Apache-2.0, ~1 GB, runs on a laptop CPU in 5-9 s per answer, good instruction following for its size, no data leaves the machine |
| Answer generation (higher quality) | **Qwen/Qwen2.5-7B-Instruct** via Hugging Face Inference Providers | Same model family, noticeably better phrasing; one env var switch (`LLM_PROVIDER=hf_inference` + `HF_TOKEN`) |
| Embeddings | **sentence-transformers/all-MiniLM-L6-v2** | Apache-2.0, 384-dim, fast on CPU, strong on short semantic search queries |

If the LLM is unavailable or errors, the system degrades to deterministic extractive answers built from the retrieved passages. It never falls back to unsupported text.

### Intake classification (hybrid, explainable)

Classification is deliberately **not** done by the LLM. A hybrid of regex signals (question phrasing, failure language, request language, catalogue items, self-heal playbook patterns) and **embedding nearest-neighbour few-shot** against labelled exemplars gives:

- deterministic, sub-50 ms decisions that work offline,
- a list of signals explaining each decision (shown in the portal under "Why the AI decided this"),
- a confidence score combining the intent margin and the category margin.

Priority comes from an ITIL impact × urgency matrix. "Cannot connect … since this morning … keeps failing" gives urgency **High**, impact **Individual** and so priority **P2**.

### RAG pipeline

1. **Documents:** markdown articles with front matter (`id`, `title`, `category`, `subcategory`, `tags`, `owner`) in `knowledge_base/` or published through the API. Metadata is stored in `knowledge_articles`.
2. **Chunking:** split on headings, then whole lines are packed into ~160-word windows with overlap. Numbered steps are never cut in half. Each chunk is embedded with its title and section for context.
3. **Embedding:** all-MiniLM-L6-v2, L2-normalised.
4. **Vector DB:** **FAISS** `IndexFlatIP` (exact cosine search; the corpus is small, so no approximation is needed), persisted to `data/vector_store/` with a fingerprint of model, chunker and content. It rebuilds automatically when anything changes. Chunks are also stored in MongoDB (`knowledge_chunks`).
5. **Retrieval:** top-k by cosine similarity, de-duplicated by section, then lightly re-ranked to prefer procedural sections and lexical overlap.
6. **Generation:** the LLM is told to answer only from the context, cite `[KBxxxx]`, and reply `INSUFFICIENT_CONTEXT` otherwise.
7. **Guards:**
   - **Relevance cut-off:** no passage ≥ `RAG_MIN_SCORE` means no answer is generated. The user is told the information isn't in the approved KB, offered a ticket, and the question is logged as a knowledge gap.
   - **Faithfulness check:** the generated answer is embedded and compared with the context. If similarity < 0.45, the answer is discarded for an extractive one.
   - **Source attribution:** every answer shows its articles, sections and similarity scores.

### AI safety and governance

- **No hallucination:** relevance cut-off + "answer only from context" prompt + faithfulness check + extractive fallback.
- **Confidence:** shown on every response, with the escalation threshold drawn on the meter.
- **Human escalation:** overall confidence < `CONFIDENCE_THRESHOLD` (0.60) creates the incident for the **Service Desk** for manual triage instead of auto-routing or automating.
- **Automation safety gates:** only allow-listed playbooks run. Identity actions require a successful MFA check and are **never** run on privileged accounts. Every action is validated against the target system, and failed validation escalates.
- **Audit:** every classification, RAG answer, automation step, ServiceNow call, approval and status change is written to `audit_logs`. Automation steps are also written to `automation_actions`. Secrets (temporary passwords) are never returned or logged.

---

## Self-heal playbooks

| Playbook | Trigger example | Mock API | Validation |
|---|---|---|---|
| `password_reset` | "My password has expired." | identity: MFA verify, reset password | `password_expired == false` |
| `account_unlock` | "My account is locked out" | identity: unlock | `locked == false` |
| `outlook_cache_clear` | "Outlook is not syncing my emails" | endpoint: clear OST cache | `outlook_sync == syncing` |
| `service_restart` | "My print jobs are stuck in the queue" | endpoint: restart Spooler | spooler running, queue empty |
| `app_restart` | "Teams is frozen and not responding" | endpoint: restart Teams | Teams running |
| `laptop_cleanup` | "My laptop is running very slow" | endpoint: temp clean-up | free disk ≥ 15% |

The VPN incident flow also runs a **non-destructive diagnostic** (`vpn_status_check`). Its findings are added to the ServiceNow work notes, and if the cause is an expired password the assistant suggests the self-heal reset.

Demo users: `emp001` Jordan Lee (password expired), `emp002` Sam Patel (account locked), `adm001` Alex Kim (privileged; automation is blocked by policy).

---

## ServiceNow integration

`integrations/servicenow.py` has two clients with the same interface:

- **`LiveServiceNowClient`** uses the REST **Table API** (`/api/now/table/{table}`) with basic auth against a Personal Developer Instance:
  - Create incident: `POST /api/now/table/incident`
  - Get incident: `GET /api/now/table/incident?sysparm_query=number=INC…`
  - Update incident: `PATCH /api/now/table/incident/{sys_id}`
  - Create service request: `POST /api/now/table/sc_request` + `POST /api/now/table/sc_req_item`
  - `sysparm_input_display_value=true` lets the assignment group be sent by name.
- **`MockServiceNowClient`** stores records in MongoDB with ServiceNow field names, numbering (`INC0010001`, `REQ0001245`, `RITM0001245`) and state codes. `/mock/servicenow/api/now/table/{table}` exposes it in the Table API's `{"result": …}` shape, so it can be called with Postman exactly like the real thing.

Switch with `SERVICENOW_MODE=live` plus the instance URL and credentials. No code changes are needed.

**AI → ServiceNow field mapping**

| AI output | Incident field |
|---|---|
| summary | `short_description` |
| employee's text | `description` |
| category / sub-category | `category` / `subcategory` |
| impact (Enterprise / Department / Individual) | `impact` (1 / 2 / 3) |
| urgency (High / Medium / Low) | `urgency` (1 / 2 / 3) |
| assignment group | `assignment_group` |
| caller | `caller_id`, `contact_type = self-service` |
| intent, confidence, suggested fix, KB, diagnostics | `work_notes`, `u_ai_intent`, `u_ai_confidence` |
| self-heal result | `state = 6 (Resolved)`, `close_code = Solved (Automated)`, `close_notes` |

In production, `u_ai_*` would be custom fields, the priority lookup would be aligned with the matrix in `ai/taxonomy.py`, and the service request would use the Service Catalog API (`/api/sn_sc/servicecatalog/items/{sys_id}/order_now`) against a real catalogue item. OAuth 2.0 would replace basic auth.

---

## API

Full interactive documentation is at `/docs`. Main endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | DB mode, LLM, vector store stats, ServiceNow mode, thresholds |
| POST | `/api/chat` | `{message, user_id, session_id?}` → reply, intent, route, confidence, actions, full ticket |
| POST | `/api/tickets` | portal form `{description, user_id, request_type: auto\|incident\|service_request}` |
| GET | `/api/tickets` | list (`type`, `status`, `user_id` filters) |
| GET | `/api/tickets/{id}` | full AI analysis with audit trail |
| PATCH | `/api/tickets/{id}` | analyst status change or work note, synced to ServiceNow |
| POST | `/api/tickets/{id}/escalate` | create a ServiceNow incident for a person |
| POST | `/api/analyze` | dry-run classification only |
| GET | `/api/servicenow/incident/{number}` | get incident from ServiceNow |
| GET | `/api/servicenow/{table}` | list incident / sc_request / sc_req_item |
| GET | `/api/kb/articles`, `/api/kb/articles/{id}`, `/api/kb/categories` | browse KB |
| GET | `/api/kb/search?q=` | raw semantic search with scores |
| POST | `/api/kb/ask` | RAG answer with sources |
| POST | `/api/kb/articles` | publish and index a new article |
| POST | `/api/kb/drafts/from-ticket/{id}` | LLM-drafted article from a ticket for review |
| GET | `/api/kb/gaps` | questions the KB couldn't answer |
| POST | `/api/kb/reindex` | re-sync `knowledge_base/` and rebuild the index |
| GET | `/api/catalog`, `/api/requests`, `/api/requests/{REQ}` | software catalogue and requests |
| POST | `/api/requests/{REQ}/approve` | `{approved, approver}` manager decision |
| GET | `/api/dashboard/stats` | dashboard metrics |
| GET | `/api/audit`, `/api/automation/runs` | audit log, automation runs |
| POST | `/api/admin/reset-demo` | clear transactional demo data |
| | `/mock/servicenow/…`, `/mock/automation/…`, `/mock/provisioning/jobs/{id}` | mock external systems |

---

## Tests

```bash
pytest                                                    # in-memory DB, extractive LLM: fast and offline
DB_MODE=mongodb MONGODB_URI="mongodb+srv://…" pytest      # against Atlas (uses database itsm_helpdesk_test)
```

[tests/test_scenarios.py](tests/test_scenarios.py) covers the five mandatory scenarios plus governance:

1. **Intelligent ticket:** the VPN text gives Incident, Network/VPN, P2, Individual/High, Network Support, "VPN authentication failure", and a ServiceNow incident with mapped fields.
2. **Self-healing:** "My password has expired" runs all 7 steps, validates the change, resolves the incident with `Solved (Automated)` and writes the audit log. A privileged account is blocked and escalated.
3. **RAG:** the Outlook synchronisation question is answered from KB0004 with citations.
4. **Software provisioning:** VS Code creates a REQ that goes Provisioning → Completed and closes the ServiceNow request. Adobe Acrobat waits for approval.
5. **Unknown question:** no answer, no sources, a knowledge gap is logged, and escalation creates a Service Desk incident.

Also covered: low-confidence escalation, incident update syncing to ServiceNow, the mock Table API shape, article publishing becoming searchable, and dashboard counts.

---

## Known limitations

- Automation, VPN, provisioning and approval systems are **mocks** with realistic state. No real accounts or devices are changed.
- The default local LLM (0.5B parameters) is small. Phrasing is occasionally clumsy, so the faithfulness check and citations matter. Use `LLM_PROVIDER=hf_inference` for better answers.
- Classification relies on English keyword signals and a modest exemplar set. A production system would fine-tune a classifier on historical tickets.
- No authentication or RBAC on the API: the portal's user switcher is for demos. Production would use SSO (OIDC) and role-based access.
- Background provisioning runs in-process (`asyncio` tasks). Production would use a durable queue (e.g. Celery or Temporal) and ServiceNow callbacks.
- FAISS `IndexFlatIP` is exact search, ideal for a small KB. A large KB would use IVF/HNSW or a managed vector DB (Atlas Vector Search, Qdrant).
- Live ServiceNow mode is implemented against the Table API but was demonstrated with the mock, since no instance credentials were available.
- macOS note: torch is imported before faiss in `app/__init__.py` because loading two OpenMP runtimes in the other order segfaults.
