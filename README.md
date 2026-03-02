# NexusAPI

NexusAPI is a multi-tenant FastAPI backend with JWT auth, Google OAuth login, credit-ledger billing, rate limiting, and async summarisation jobs.

## What This Project Includes

The backend exposes tenant-aware APIs for user identity, credit grants and balance, text analysis, and async summarisation. Credit usage is tracked in a ledger model instead of a single mutable balance field. Background summarisation jobs are queued with Redis/ARQ and can be polled with job status endpoints.

Main backend endpoints:

- `GET /health`
- `GET /auth/google`
- `GET /auth/callback`
- `GET /me`
- `POST /credits/grant`
- `GET /credits/balance`
- `POST /api/analyse`
- `POST /api/summarise`
- `GET /api/jobs/{job_id}`

## Tech Stack

- FastAPI
- SQLAlchemy (async)
- Alembic
- PostgreSQL (Neon compatible)
- Redis (Upstash compatible)
- ARQ worker

## Project Layout

- `app/` backend code
- `alembic/` migration config and scripts
- `tests/` test suite
- `frontend/` static HTML/CSS/JS client
- `.env.example` env template
- `cloudrun.env.yaml` Cloud Run environment values

## Prerequisites

- Python 3.11+
- PostgreSQL or Neon database
- Redis or Upstash Redis
- Google OAuth client credentials

## Local Setup (Windows PowerShell)

Run these commands one by one:

```powershell
cd D:\nexusapi_2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create env file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set real values.

## Required `.env` Values

At minimum, set these values correctly:

```env
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>/<db>?ssl=require
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=<long-random-secret-at-least-32-chars>
GOOGLE_CLIENT_ID=<google-client-id>
GOOGLE_CLIENT_SECRET=<google-client-secret>
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
FRONTEND_OAUTH_SUCCESS_URL=http://localhost:5500
CORS_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_FAIL_OPEN=true
```

For Neon, keep `?ssl=require` in `DATABASE_URL`.

For Upstash, `REDIS_URL` is usually `rediss://...`.

## Database Migration

```powershell
alembic upgrade head
```

If migration fails, confirm `DATABASE_URL` in `.env` is valid and reachable.

## Run Backend

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

- API root: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## Run Worker (for `/api/summarise`)

In a second terminal:

```powershell
cd D:\nexusapi_2
.\.venv\Scripts\Activate.ps1
arq app.jobs.worker.WorkerSettings
```

## Run Frontend

In a third terminal:

```powershell
cd D:\nexusapi_2\frontend
python -m http.server 5500
```

Open `http://localhost:5500`.

## Google OAuth Setup

Create OAuth credentials in Google Cloud Console:

1. Create/select project.
2. Configure OAuth consent screen.
3. Create OAuth client type `Web application`.
4. Add Authorized redirect URI matching backend callback.

For local:

- `http://localhost:8000/auth/callback`
- `http://127.0.0.1:8000/auth/callback`

For Cloud Run production, also add your real callback:

- `https://<your-cloud-run-domain>/auth/callback`

Then set matching env values in backend.

If Google shows a 400 malformed request page, the redirect URI configured in Google usually does not exactly match `GOOGLE_REDIRECT_URI` used by backend.

## Cloud Run Backend Deployment

Build and push image:

```powershell
gcloud builds submit --tag gcr.io/<PROJECT_ID>/nexusapi
```

Deploy:

```powershell
gcloud run deploy nexusapi --image gcr.io/<PROJECT_ID>/nexusapi --region us-central1 --platform managed --allow-unauthenticated --memory 512Mi --port 8080 --env-vars-file D:\nexusapi_2\cloudrun.env.yaml
```

Recommended production env values:

- `FRONTEND_OAUTH_SUCCESS_URL=https://<your-vercel-domain>`
- `CORS_ORIGINS=https://<your-vercel-domain>`
- `GOOGLE_REDIRECT_URI=https://<your-cloud-run-domain>/auth/callback`

After deploy, verify:

```powershell
Invoke-WebRequest -UseBasicParsing https://<your-cloud-run-domain>/health
Invoke-WebRequest -UseBasicParsing https://<your-cloud-run-domain>/auth/google
```

Expected:

- `/health` returns 200 with healthy JSON
- `/auth/google` returns redirect (307/302)

## Vercel Frontend Deployment

Deploy `frontend/` as a static site on Vercel.

After deploy:

1. Open frontend URL.
2. Set API Base URL field to your Cloud Run backend URL.
3. Keep backend CORS and OAuth success URL aligned with Vercel domain.

No frontend secrets are required for this static client.

## Quick API Checks

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/auth/google
```

Swagger UI:

- `http://127.0.0.1:8000/docs`

## Common Problems

If backend crashes with missing `database_url`, `redis_url`, `jwt_secret`, `.env` is missing or not loaded correctly. Keep `.env` in repo root (`D:\nexusapi_2\.env`).

If frontend shows API errors from `localhost:8000` while deployed on Vercel, change API Base URL in the UI to Cloud Run URL.

If `/auth/google` returns not found in deployed backend, verify OAuth router is included in app startup and deployment image is rebuilt from latest source.

If Cloud Run revision does not become ready, check logs and confirm app binds to `PORT` in container startup command.

## Tests

```powershell
pytest tests -v
```

## Notes

- Architecture details are in `ARCHITECTURE.md`.
- Design tradeoff rationale is in `DECISIONS.md`.
