# NexusAPI — Task Breakdown (GSD Output)

## Task Planner: Atomic, Testable, < 1 Hour Each

---

## Phase A: Foundation

### Task A1: Project Bootstrap & Dependencies

**Task ID:** A1  
**Description:** Create `pyproject.toml` or `requirements.txt` with all dependencies: FastAPI, SQLAlchemy 2.0 (async), Alembic, asyncpg, redis, arq, PyJWT, httpx, pydantic-settings, structlog. Add `.env.example` with required env vars.  
**Expected Output:** `requirements.txt` or `pyproject.toml`, `.env.example`  
**Validation Criteria:** `pip install -r requirements.txt` succeeds; all packages importable  
**Dependencies:** None

---

### Task A2: Core Configuration Module

**Task ID:** A2  
**Description:** Implement `app/core/config.py` using pydantic-settings. Load DATABASE_URL, REDIS_URL, JWT_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, RATE_LIMIT_PER_ORG, etc. from environment.  
**Expected Output:** `app/core/config.py` with `Settings` class  
**Validation Criteria:** Config loads from env; unit test verifies overrides  
**Dependencies:** A1

---

### Task A3: Structured Logging Setup

**Task ID:** A3  
**Description:** Implement `app/core/logging.py` using structlog. Configure JSON output for production, console for dev. Integrate with FastAPI lifespan.  
**Expected Output:** `app/core/logging.py`, logging configured in main app  
**Validation Criteria:** Logs are structured; request_id propagates  
**Dependencies:** A1

---

### Task A4: Database Connection & Session Factory

**Task ID:** A4  
**Description:** Implement `app/core/database.py` with async SQLAlchemy engine, `async_sessionmaker`, and `get_db` dependency. Use `create_async_engine` with `pool_pre_ping`, `echo` configurable.  
**Expected Output:** `app/core/database.py`, `get_db` async generator  
**Validation Criteria:** Session creates; connection pool works; unit test for session lifecycle  
**Dependencies:** A2

---

## Phase B: Models & Migrations

### Task B1: Organisation & User Models

**Task ID:** B1  
**Description:** Create `app/models/organisation.py` and `app/models/user.py`. Organisation: id (UUID), name, created_at, updated_at. User: id (UUID), email, google_sub, organisation_id (FK), created_at, updated_at. Use `mapped_column`, `relationship`.  
**Expected Output:** `app/models/organisation.py`, `app/models/user.py`  
**Validation Criteria:** Models import; relationships resolve; no syntax errors  
**Dependencies:** A4

---

### Task B2: CreditTransaction Model

**Task ID:** B2  
**Description:** Create `app/models/credit_transaction.py`. Columns: id (UUID), organisation_id (FK), user_id (FK nullable), amount (INT), reason (TEXT), idempotency_key (TEXT UNIQUE nullable), created_at. Add unique constraint on idempotency_key. Index on (organisation_id, created_at).  
**Expected Output:** `app/models/credit_transaction.py`  
**Validation Criteria:** Model imports; unique constraint defined; index defined  
**Dependencies:** B1

---

### Task B3: Alembic Initial Setup

**Task ID:** B3  
**Description:** Configure Alembic: `alembic.ini`, `alembic/env.py` with async support, `alembic/script.py.mako`. Point to `app.models` for autogenerate.  
**Expected Output:** `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`  
**Validation Criteria:** `alembic current` runs; `alembic revision --autogenerate` generates migration  
**Dependencies:** B2, A4

---

### Task B4: Initial Migration

**Task ID:** B4  
**Description:** Create and apply initial migration for Organisation, User, CreditTransaction. Ensure idempotency_key has UNIQUE constraint.  
**Expected Output:** `alembic/versions/xxx_initial.py`, migration applies cleanly  
**Validation Criteria:** `alembic upgrade head` succeeds; tables exist in DB  
**Dependencies:** B3

---

## Phase C: Schemas & Core Security

### Task C1: Pydantic Schemas (Organisation, User, Credit)

**Task ID:** C1  
**Description:** Create `app/schemas/organisation.py`, `app/schemas/user.py`, `app/schemas/credit.py`. Include request/response schemas for credit deduction, balance, transaction.  
**Expected Output:** Schema modules with Create, Read, CreditDeductionRequest, CreditBalanceResponse, etc.  
**Validation Criteria:** Schemas validate correctly; serialization works  
**Dependencies:** B2

---

### Task C2: JWT Utilities

**Task ID:** C2  
**Description:** Implement `app/core/security.py` with `create_access_token`, `decode_token`, `get_current_user` dependency. JWT payload: sub (user_id), org_id, exp.  
**Expected Output:** `app/core/security.py`  
**Validation Criteria:** Token creation and validation work; expired token rejected  
**Dependencies:** A2

---

### Task C3: Google OAuth Flow

**Task ID:** C3  
**Description:** Implement `app/services/auth_service.py`: exchange Google code for tokens, fetch user info, upsert User by google_sub, link to Organisation (create or select). Return user + org for JWT creation.  
**Expected Output:** `app/services/auth_service.py` with `authenticate_google(code)`  
**Validation Criteria:** Unit test with mocked Google response; user created/updated  
**Dependencies:** B1, A2

---

## Phase D: Middleware

### Task D1: Authentication Middleware / Dependency

**Task ID:** D1  
**Description:** Implement `app/middleware/auth.py` or extend `get_current_user` to extract JWT from Authorization header, validate, inject user and org_id into request state.  
**Expected Output:** Auth dependency that returns (user, organisation_id)  
**Validation Criteria:** Protected route rejects missing/invalid token; accepts valid token  
**Dependencies:** C2

---

### Task D2: Tenant Context Middleware

**Task ID:** D2  
**Description:** Ensure `organisation_id` from JWT is stored in request state/context. All service calls receive org_id from this context, never from request body for scoping.  
**Expected Output:** Middleware or dependency that sets `request.state.org_id`  
**Validation Criteria:** Org ID propagates to services; cannot be overridden by client  
**Dependencies:** D1

---

### Task D3: Rate Limiting Middleware (Per Organisation)

**Task ID:** D3  
**Description:** Implement `app/middleware/rate_limit.py` using Redis. Key: `ratelimit:{org_id}:{minute}`. Increment, check against RATE_LIMIT_PER_ORG. On Redis failure: configurable fail-open or fail-closed.  
**Expected Output:** `app/middleware/rate_limit.py`, rate limit dependency  
**Validation Criteria:** Requests over limit return 429; Redis failure handled per config  
**Dependencies:** A2, D2

---

### Task D4: Request Logging Middleware

**Task ID:** D4  
**Description:** Add middleware to log request method, path, org_id, user_id, status, duration. Use structlog.  
**Expected Output:** Logging middleware integrated in FastAPI app  
**Validation Criteria:** Logs contain expected fields  
**Dependencies:** A3, D1

---

## Phase E: Credit Service

### Task E1: Credit Balance Query

**Task ID:** E1  
**Description:** Implement `app/services/credit_service.py` with `get_balance(org_id: UUID) -> int`. Query: `SELECT COALESCE(SUM(amount), 0) FROM credit_transactions WHERE organisation_id = :org_id`.  
**Expected Output:** `get_balance` function, async, returns int  
**Validation Criteria:** Unit test: insert transactions, verify balance  
**Dependencies:** B2, A4

---

### Task E2: Atomic Credit Deduction (No Idempotency)

**Task ID:** E2  
**Description:** Implement `deduct_credits(org_id, user_id, amount, reason)` without idempotency. Use transaction, `SELECT ... FOR UPDATE` or advisory lock on org, compute balance, check balance >= amount, INSERT negative row. Return transaction or raise InsufficientCreditsError.  
**Expected Output:** `deduct_credits` with atomicity and balance check  
**Validation Criteria:** Concurrency test: N parallel deductions, balance never negative; unit test for insufficient credits  
**Dependencies:** E1

---

### Task E3: Idempotent Credit Deduction

**Task ID:** E3  
**Description:** Extend deduction to accept `idempotency_key`. On INSERT, catch UniqueViolation for idempotency_key; if caught, SELECT existing row and return it (do not deduct again).  
**Expected Output:** `deduct_credits(..., idempotency_key=None)` with idempotency support  
**Validation Criteria:** Same idempotency_key twice returns same result; only one row inserted  
**Dependencies:** E2

---

### Task E4: Credit Top-Up (Admin/System)

**Task ID:** E4  
**Description:** Implement `add_credits(org_id, amount, reason, user_id=None)` for positive transactions. No idempotency required for top-up (or optional).  
**Expected Output:** `add_credits` function  
**Validation Criteria:** Balance increases correctly; unit test  
**Dependencies:** E1

---

## Phase F: API Endpoints

### Task F1: Health & Readiness Endpoints

**Task ID:** F1  
**Description:** Implement `GET /health` (liveness), `GET /ready` (DB + Redis connectivity).  
**Expected Output:** Endpoints in `app/api/health.py`  
**Validation Criteria:** Health returns 200; ready returns 503 if DB/Redis down  
**Dependencies:** A4, A2

---

### Task F2: Auth Endpoints (Google OAuth Callback)

**Task ID:** F2  
**Description:** Implement `POST /auth/google` (body: `{ code }`), `GET /auth/me`. Call auth_service, create JWT, return token.  
**Expected Output:** `app/api/auth.py`  
**Validation Criteria:** OAuth flow returns JWT; /auth/me returns user with valid token  
**Dependencies:** C3, C2, D1

---

### Task F3: Credit Endpoints

**Task ID:** F3  
**Description:** Implement `GET /credits/balance`, `POST /credits/deduct` (body: amount, reason, idempotency_key). Both require auth. Use org_id from JWT.  
**Expected Output:** `app/api/credits.py`  
**Validation Criteria:** Balance returns correct sum; deduct reduces balance; idempotent deduct returns same result; 402 on insufficient credits  
**Dependencies:** E3, D1, D2

---

### Task F4: Organisation & User Endpoints (Optional CRUD)

**Task ID:** F4  
**Description:** Implement `GET /organisations/me`, `GET /users/me` for current org and user. Admin endpoints for credit top-up if needed.  
**Expected Output:** `app/api/organisations.py`, `app/api/users.py`  
**Validation Criteria:** Returns correct org/user for JWT  
**Dependencies:** F2, D1

---

## Phase G: ARQ Jobs

### Task G1: ARQ Worker Setup

**Task ID:** G1  
**Description:** Configure ARQ: Redis connection, worker entrypoint. Create `app/jobs/worker.py` with `on_startup`, `on_shutdown`.  
**Expected Output:** `app/jobs/worker.py`, worker runnable via `arq app.jobs.worker.WorkerSettings`  
**Validation Criteria:** Worker starts; connects to Redis  
**Dependencies:** A2

---

### Task G2: Sample Async Job (Credit Top-Up)

**Task ID:** G2  
**Description:** Implement job `top_up_credits(org_id, amount, reason)` that calls credit_service.add_credits. Enqueue from API or CLI.  
**Expected Output:** Job in `app/jobs/tasks.py`, enqueue function  
**Validation Criteria:** Job runs; credits added; test with ARQ worker  
**Dependencies:** G1, E4

---

### Task G3: Job Failure Handling

**Task ID:** G3  
**Description:** Configure retries, max_jobs, job_timeout. Ensure job failures do not crash worker. Add dead-letter or logging for permanent failures.  
**Expected Output:** Robust worker config, failure handling  
**Validation Criteria:** Failing job retries; worker stays up  
**Dependencies:** G2

---

## Phase H: Main Application & Docker

### Task H1: FastAPI Application Assembly

**Task ID:** H1  
**Description:** Create `app/main.py`: FastAPI app, lifespan (DB pool, Redis, logging), include routers (health, auth, credits, orgs, users), add middleware (auth, rate limit, logging).  
**Expected Output:** `app/main.py`, runnable via `uvicorn app.main:app`  
**Validation Criteria:** App starts; all routes registered; middleware applied  
**Dependencies:** F1, F2, F3, F4, D3, D4

---

### Task H2: Docker Configuration

**Task ID:** H2  
**Description:** Create `Dockerfile` (Python 3.11, install deps, run uvicorn), `docker-compose.yml` (app, postgres, redis, arq-worker).  
**Expected Output:** `Dockerfile`, `docker-compose.yml`  
**Validation Criteria:** `docker-compose up` brings up all services; API responds  
**Dependencies:** H1, G1

---

## Phase I: Testing

### Task I1: Unit Tests (Credit Service)

**Task ID:** I1  
**Description:** Tests for get_balance, deduct_credits, add_credits, idempotency. Use in-memory SQLite or test DB.  
**Expected Output:** `tests/test_credit_service.py`  
**Validation Criteria:** All tests pass; coverage for happy path and error cases  
**Dependencies:** E3, E4

---

### Task I2: Concurrency Tests (Credit Deduction)

**Task ID:** I2  
**Description:** Test N concurrent deductions; assert balance never negative, final balance correct. Use asyncio or pytest-asyncio with multiple coroutines.  
**Expected Output:** `tests/test_credit_concurrency.py`  
**Validation Criteria:** No race conditions; balance consistent  
**Dependencies:** E3

---

### Task I3: Idempotency Tests

**Task ID:** I3  
**Description:** Test duplicate idempotency_key returns same result; only one DB row.  
**Expected Output:** `tests/test_credit_idempotency.py`  
**Validation Criteria:** Duplicate key returns existing; no double deduction  
**Dependencies:** E3

---

### Task I4: Multi-Tenant Isolation Tests

**Task ID:** I4  
**Description:** Test that org A cannot access org B's credits, balance, or transactions.  
**Expected Output:** `tests/test_tenant_isolation.py`  
**Validation Criteria:** Cross-tenant access blocked or returns empty/403  
**Dependencies:** F3, D2

---

### Task I5: API Integration Tests

**Task ID:** I5  
**Description:** End-to-end tests: auth flow, credit balance, deduct, idempotent deduct. Use TestClient.  
**Expected Output:** `tests/test_api_integration.py`  
**Validation Criteria:** Full flow works; status codes correct  
**Dependencies:** H1

---

## Phase J: Documentation & Finalisation

### Task J1: DECISIONS.md

**Task ID:** J1  
**Description:** Document key decisions: ledger vs balance column, idempotency strategy, rate limit fail-open/closed, etc.  
**Expected Output:** `DECISIONS.md`  
**Validation Criteria:** All major design choices documented  
**Dependencies:** All prior

---

### Task J2: VERSION.md & README

**Task ID:** J2  
**Description:** Create VERSION.md (semver), README.md with setup, run, test instructions.  
**Expected Output:** `VERSION.md`, `README.md`  
**Validation Criteria:** New developer can follow README to run project  
**Dependencies:** H2

---

## Task Dependency Graph (Summary)

```
A1 → A2 → A4
A1 → A3
A4, B1 → B2 → B3 → B4
B2 → C1
A2 → C2 → D1 → D2 → D3, D4
B1, A2 → C3
E1 → E2 → E3, E4
E3, D1, D2 → F3
C3, C2, D1 → F2
A4, A2 → F1
F2, D1 → F4
A2 → G1 → G2 → G3
F1..F4, D3, D4 → H1 → H2
E3, E4 → I1, I2, I3
F3, D2 → I4
H1 → I5
```

---

## Execution Order (Ralph Loop)

Execute in order: **A1 → A2 → A3 → A4 → B1 → B2 → B3 → B4 → C1 → C2 → C3 → D1 → D2 → D3 → D4 → E1 → E2 → E3 → E4 → F1 → F2 → F3 → F4 → G1 → G2 → G3 → H1 → H2 → I1 → I2 → I3 → I4 → I5 → J1 → J2**

**One task at a time. No parallel execution.**
