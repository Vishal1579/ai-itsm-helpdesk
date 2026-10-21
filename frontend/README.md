# AI-Powered ITSM Helpdesk: portal

React + TypeScript (Vite) employee portal for the AI ITSM helpdesk. The FastAPI backend is at the root of this repository; see the [main README](../README.md) for architecture, AI design and API docs.

## Screens

| Route | Screen | Shows |
|---|---|---|
| `/` | **Get help** (employee self-service) | AI chatbot, request form, suggested resolution, create-ticket option, and a live *What the AI decided* panel |
| `/dashboard` | **ITSM dashboard** | Total, open, AI-resolved and escalated tickets; software requests; automation outcomes; breakdowns by intent, category and priority |
| `/tickets`, `/tickets/:id` | **Tickets & AI analysis** | Intent, category, priority, confidence vs threshold, signals, resolution, KB sources, self-heal decision trace, diagnostics, live ServiceNow record and work notes, timeline, audit trail |
| `/knowledge` | **Knowledge base** | Articles by category, filter, RAG *Ask* with retrieved passages and similarity scores, unanswered questions, publish or review AI-drafted articles |
| `/software` | **Software** | Approved catalogue, requests with live provisioning progress, manager approval |

## Run

```bash
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api` and `/mock` to the backend on `http://localhost:8000`, so start the backend first (`uvicorn app.main:app --port 8000` from the repository root).

```bash
npm run build        # type-check and production build into dist/
```

## Notes

- No UI framework: hand-written CSS with design tokens in `src/index.css`, with light and dark themes via `prefers-color-scheme`. Fonts are Onest and IBM Plex Mono (used only for system IDs such as INC/REQ/KB numbers).
- `src/api.ts` holds the typed API client and the shared types that mirror the backend's ticket model.
- The signed-in user switcher in the sidebar is a demo convenience. Try *Alex Kim (admin)* to see automation blocked by policy.
