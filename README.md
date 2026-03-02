# NexusAPI

NexusAPI is a multi-tenant FastAPI backend with JWT authentication, Google OAuth onboarding, a credit-ledger billing model, and credit-gated product endpoints for synchronous analysis and asynchronous summarisation backed by Redis/ARQ workers.

## Prerequisites

- Python 3.11+
- PostgreSQL (local) or Neon Postgres
- Redis

## Local Setup

1. Clone and enter the repository:

```bash
git clone <your-repo-url>
cd nexusapi_2
```

2. Create and activate a virtual environment:

```bash
# Windows
python -m venv venv && venv\Scripts\activate

# Mac/Linux
python -m venv venv && source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create environment file:

```bash
cp .env.example .env
```

Then edit `.env` with real values.

### Use Neon DB

Set `DATABASE_URL` in `.env` to your Neon connection string:

```bash
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<neon-host>/<db_name>?ssl=require
```

Then run migrations normally:

```bash
alembic upgrade head
```

5. Run database migrations:

```bash
alembic upgrade head
```

6. Start the API:

```bash
uvicorn app.main:app --reload
```

## Environment Variables

| Name | Description | Example |
| --- | --- | --- |
| `DATABASE_URL` | Async SQLAlchemy database connection URL. | `postgresql+asyncpg://user:password@localhost:5432/nexusapi` |
| `REDIS_URL` | Redis connection URL used for rate-limit and worker queue infrastructure. | `redis://localhost:6379/0` |
| `JWT_SECRET` | Secret used to sign JWT access tokens (minimum 32 chars). | `super-long-secret-key-at-least-32-chars` |
| `JWT_ALGORITHM` | JWT signing algorithm. | `HS256` |
| `JWT_EXPIRE_MINUTES` | Configured JWT expiry duration in minutes. | `60` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID for login. | `your-google-client-id.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret for token exchange. | `your-google-client-secret` |
| `GOOGLE_REDIRECT_URI` | Redirect URI configured in Google OAuth app. | `http://localhost:8000/auth/callback` |
| `FRONTEND_OAUTH_SUCCESS_URL` | Frontend URL to receive token after OAuth success. | `http://localhost:5500` |
| `RATE_LIMIT_PER_MINUTE` | Allowed requests per minute per key. | `100` |
| `RATE_LIMIT_WINDOW_SECONDS` | Sliding/fixed rate-limit window in seconds. | `60` |
| `RATE_LIMIT_FAIL_OPEN` | If `true`, allow requests when limiter backend is unavailable. | `true` |
| `ENVIRONMENT` | Runtime environment label. | `development` |
| `DEBUG` | Enables debug behavior/log verbosity toggles where supported. | `false` |
| `LOG_LEVEL` | Base application log level. | `INFO` |
| `CORS_ORIGINS` | Comma-separated frontend origins allowed to call API. | `http://localhost:5500,http://127.0.0.1:5500` |

Optional OAuth callback override: `GOOGLE_REDIRECT_URI` (default is `http://localhost:8000/auth/callback`).

Neon example for `DATABASE_URL`: `postgresql+asyncpg://<user>:<password>@<neon-host>/<db_name>?ssl=require`

## Run with Docker

```bash
docker-compose up --build
```

## Run Tests

```bash
pytest tests/ -v
```

## Google OAuth Setup

1. Open Google Cloud Console and create/select a project.
2. Go to `APIs & Services -> OAuth consent screen` and configure app name, support email, and test users.
3. Go to `APIs & Services -> Credentials -> Create Credentials -> OAuth client ID`.
4. Choose `Web application`.
5. Add authorized redirect URI: `http://localhost:8000/auth/callback`.
6. Copy generated Client ID and Client Secret into `.env`:

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
FRONTEND_OAUTH_SUCCESS_URL=http://localhost:5500
```

7. Start backend and frontend.
8. Open frontend and click `Sign in with Google`.

## API Examples

1. Health check:

```bash
curl -X GET "http://localhost:8000/health"
```

2. Google OAuth start (open in browser to continue consent flow):

```bash
curl -i -X GET "http://localhost:8000/auth/google"
```

3. Grant credits (admin token required):

```bash
curl -X POST "http://localhost:8000/credits/grant" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"amount\":100,\"reason\":\"manual_grant\"}"
```

4. Get credit balance:

```bash
curl -X GET "http://localhost:8000/credits/balance" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

5. Analyse text:

```bash
curl -X POST "http://localhost:8000/api/analyse" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"This is a sample document long enough for analysis.\"}"
```

6. Summarise text:

```bash
curl -X POST "http://localhost:8000/api/summarise" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"This is a sample document long enough for summarisation background processing.\"}"
```

7. Check async job status:

```bash
curl -X GET "http://localhost:8000/api/jobs/<JOB_ID>" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

## Architecture

System design, module boundaries, and request/worker flow details are documented in `ARCHITECTURE.md`.

## Decisions

Implementation tradeoffs and rationale are documented in `DECISIONS.md`.
