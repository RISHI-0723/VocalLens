# VocalLens — Deployment Guide

This document describes how VocalLens is deployed and how to reproduce it.

## Architecture

```
  Browser
     │  HTTPS
     ▼
  Vercel (static React/Vite SPA)            ──VITE_API_BASE──►   Render (FastAPI + engine)
  https://vocallens-eosin.vercel.app                            https://vocallens-api.onrender.com
     • built from /frontend                                        • built from repo root
     • SPA rewrites (frontend/vercel.json)                         • render.yaml blueprint
     • calls ${VITE_API_BASE}/api/...                              • /api/* routes, /docs, audio bytes
```

The frontend is **static** — it holds no secrets and does no analysis. All analysis,
feature extraction, scoring and exports run on the FastAPI backend through the single
`analyze_pair()` pipeline. The backend bundles the committed **synthetic** dataset under
`data/samples/` and `data/annotations/`, so it is self-contained (no external storage).

## Live URLs

| Piece    | URL                                            | Status |
|----------|------------------------------------------------|--------|
| Frontend | https://vocallens-eosin.vercel.app             | Deployed (Vercel) |
| Backend  | https://vocallens-api.onrender.com             | Pending Render blueprint (see below) |
| Health   | https://vocallens-api.onrender.com/api/health  | Live once the backend deploys |
| API docs | https://vocallens-api.onrender.com/docs        | Live once the backend deploys |

> The frontend production build already points at the backend URL above. The moment the
> Render service is live at that hostname, the live site connects with no rebuild.

---

## Part A — Backend on Render (manual, one-time browser auth)

The Render CLI is not authenticated in this environment, so creating the service is a
short dashboard action. Everything it needs is already committed (`render.yaml`,
`requirements-render.txt`).

1. Go to <https://dashboard.render.com> and sign in (GitHub login).
2. **New → Blueprint**.
3. Connect / authorize the GitHub repo **`RISHI-0723/VocalLens`** and pick the
   `submission-finalization` branch (or `main` after you merge).
4. Render reads `render.yaml` and proposes a **web service** named `vocallens-api`.
   Keep the name `vocallens-api` so the public URL is
   `https://vocallens-api.onrender.com` (the frontend is already configured for it).
   If that subdomain is taken, Render will assign a different one — then update
   `VITE_API_BASE` on Vercel (Part B, step 2) and redeploy the frontend.
5. Click **Apply**. First build installs the lean runtime deps and takes a few minutes.
6. Verify: `curl https://vocallens-api.onrender.com/api/health` → `{"status":"ok",...}`.

Settings baked into `render.yaml`:
- Build: `pip install --upgrade pip && pip install -r requirements-render.txt`
- Start: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/api/health`
- `PYTHON_VERSION=3.11.9`
- `VOCALLENS_CORS_ORIGINS=https://vocallens-eosin.vercel.app`
- `VOCALLENS_CORS_ORIGIN_REGEX=https://vocallens-.*\.vercel\.app` (allows previews)

### Free-tier limits (honest)
- The service **spins down after ~15 min idle**; the next request cold-starts (~30–50s).
  The frontend shows a transient "API offline / waking up" banner and auto-reconnects.
- Filesystem is **ephemeral**. VocalLens needs no persistence: uploads are processed in a
  temp file then deleted; results sit in a bounded in-memory cache only long enough to
  export them. Export links stop working after a restart or once evicted (expected).

## Part B — Frontend on Vercel (already deployed)

Already deployed via the Vercel CLI (project `rishi-6e83/vocallens`). To reproduce:

1. From `frontend/`: `vercel link --yes --project vocallens`
2. Set the backend origin (build-time, so set it **before** deploying):
   `printf "https://vocallens-api.onrender.com" | vercel env add VITE_API_BASE production`
3. `vercel deploy --prod --yes`

Vercel project settings (also in `frontend/vercel.json`):
- Framework: **Vite** · Root directory: **frontend** · Build: `npm run build` · Output: `dist`
- SPA rewrite sends all paths to `index.html` so `/analysis` and `/evaluation` work on
  direct navigation and refresh. The rewrite does **not** touch backend calls — those go
  to the absolute `VITE_API_BASE` origin, not to Vercel.

### Optional: auto-deploy on git push
`vercel git connect` (or connect the repo in the Vercel dashboard) if you want every push
to redeploy. The CLI attempt to auto-connect needs the Vercel GitHub app authorized once.

## Secrets
None are required. No API keys or tokens are committed. `VITE_`-prefixed variables are
public by design, so only the backend **URL** lives there — never a secret. The backend
needs no secrets for the synthetic demo.
