# NexusAPI — Multi-Tenant Credit-Gated Backend

## Project Overview

NexusAPI is a production-grade FastAPI backend system implementing multi-tenant organisation isolation, Google OAuth authentication, JWT-based authorization, and a transaction-based credit ledger system with atomic, idempotent credit deduction.

## Objective

Build a backend system that is:

- **Production-safe** — Handles concurrency, failures, and edge cases correctly
- **Multi-tenant** — Strict database-level organisation isolation
- **Credit-gated** — Ledger-based credits with atomic deduction and idempotency
- **Async-first** — Redis + ARQ for background job processing
- **Failure-safe** — Graceful degradation and consistent state under failure

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Framework | FastAPI |
| Database | PostgreSQL |
| ORM | Async SQLAlchemy 2.0 |
| Migrations | Alembic |
| Authentication | Google OAuth + JWT |
| Cache | Redis |
| Job Queue | ARQ |
| Deployment | Docker compatible |

## Critical Design Principles

### Credit System

- **No stored balance** — Credit balance is derived from ledger sum only
- **Atomic deduction** — Database transaction + row-level locking
- **Idempotent** — Unique constraint on `idempotency_key` at database level
- **Concurrent-safe** — No race conditions under parallel deduction

### Multi-Tenancy

- **Strict isolation** — All queries scoped by `organisation_id`
- **Database-level enforcement** — Row-level security and FK constraints
- **No cross-tenant access** — Middleware and service layer validation

### Failure Handling

- **Redis failure** — Graceful degradation, no crash
- **Database failure** — Transaction rollback, no partial state
- **Job failure** — Retry with idempotency, dead-letter handling

## Project Structure

```
nexusapi_2/
├── app/
│   ├── api/          # Route handlers, endpoints
│   ├── core/         # Config, security, logging
│   ├── models/       # SQLAlchemy models
│   ├── schemas/      # Pydantic schemas
│   ├── services/     # Business logic
│   ├── middleware/   # Rate limiting, auth, logging
│   └── jobs/         # ARQ job definitions
├── tests/            # Unit, integration, concurrency tests
├── alembic/          # Database migrations
├── PROJECT.md
├── TASKS.md
├── ARCHITECTURE.md
├── DECISIONS.md
├── REVIEW.md
├── INTEGRATION_REPORT.md
└── VERSION.md
```

## Success Criteria

- [ ] Multi-tenant organisation isolation enforced at database level
- [ ] Google OAuth + JWT authentication working
- [ ] Credit ledger with atomic, idempotent deduction
- [ ] No negative credit balance possible
- [ ] No duplicate credit deduction for same idempotency key
- [ ] No cross-tenant data leakage
- [ ] Async jobs via Redis + ARQ
- [ ] Rate limiting per organisation
- [ ] Structured logging
- [ ] All concurrency and failure tests pass

## Status

**Phase:** Design Complete — Awaiting Execution Command

**Next:** Ralph Loop (Execution Agent) to implement tasks from TASKS.md
