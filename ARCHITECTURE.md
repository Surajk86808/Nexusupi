# NexusAPI — Architecture Document

## Architect Validator: Design Integrity Report

**Status:** VALIDATED  
**Date:** 2025-02-28

---

## 1. Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Layer (app/api)                       │
│  Route handlers, request/response, dependency injection          │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Middleware (app/middleware)                    │
│  Auth, rate limiting, logging, tenant context                    │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Services Layer (app/services)                   │
│  Business logic, credit operations, tenant-scoped queries         │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Models Layer (app/models)                      │
│  SQLAlchemy models, repository pattern, DB operations            │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PostgreSQL Database                         │
└─────────────────────────────────────────────────────────────────┘

Parallel:
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│     Redis       │  │   ARQ Workers    │  │  Core (config)   │
│  Cache, rate    │  │  Background jobs │  │  Logging, auth   │
│  limit state   │  │                  │  │                  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## 2. Critical Safety Guarantees

### 2.1 Credit Race Condition Prevention

| Mechanism | Implementation |
|-----------|----------------|
| **No stored balance** | Balance = `SUM(amount)` from `CreditTransactions` |
| **Row-level locking** | `SELECT ... FOR UPDATE` on organisation row or advisory lock |
| **Atomic transaction** | Deduction + insert in single DB transaction |
| **Serialization** | Lock organisation before computing balance and inserting |

**Flow:**
1. Begin transaction
2. `SELECT ... FOR UPDATE` or advisory lock on `(organisation_id)` 
3. Compute `balance = SUM(amount) WHERE organisation_id = ?`
4. If `balance >= amount`: INSERT negative transaction
5. Commit (or rollback on any failure)

### 2.2 Cross-Tenant Data Leakage Prevention

| Layer | Enforcement |
|-------|-------------|
| **API** | `organisation_id` from JWT/context, never from request body for scoping |
| **Services** | All queries require `organisation_id` parameter |
| **Models** | FK `organisation_id` on all tenant-scoped tables |
| **Database** | RLS (optional) or application-level enforcement |

**Rule:** Every tenant-scoped query MUST include `organisation_id` from authenticated context.

### 2.3 Duplicate Credit Deduction Prevention

| Mechanism | Implementation |
|-----------|----------------|
| **Idempotency key** | `idempotency_key TEXT UNIQUE` on `CreditTransactions` |
| **Database constraint** | `UNIQUE(idempotency_key)` where `idempotency_key IS NOT NULL` |
| **Application** | On duplicate key: return existing transaction, do not deduct again |

**Flow:**
1. Client sends `idempotency_key` with deduction request
2. Attempt INSERT with `idempotency_key`
3. On `UniqueViolation`: SELECT existing row, return it (idempotent response)
4. On success: return new transaction

### 2.4 Inconsistent Ledger State Prevention

| Mechanism | Implementation |
|-----------|----------------|
| **Single source of truth** | Only `CreditTransactions` table; no balance column |
| **ACID transactions** | All credit operations in transaction |
| **No partial commits** | Rollback on any error |
| **Audit trail** | Every change is append-only transaction row |

---

## 3. Data Model

### 3.1 Core Tables

```
Organisation
├── id UUID PK
├── name TEXT
├── created_at TIMESTAMP
└── updated_at TIMESTAMP

User
├── id UUID PK
├── email TEXT UNIQUE
├── google_sub TEXT UNIQUE
├── organisation_id UUID FK → Organisation
├── created_at TIMESTAMP
└── updated_at TIMESTAMP

CreditTransaction
├── id UUID PK
├── organisation_id UUID FK → Organisation (NOT NULL)
├── user_id UUID FK → User (nullable for system ops)
├── amount INT (positive = credit, negative = debit)
├── reason TEXT
├── idempotency_key TEXT UNIQUE NULLABLE
├── created_at TIMESTAMP
└── (index on organisation_id, created_at for balance queries)
```

### 3.2 Credit Balance Derivation

```sql
SELECT COALESCE(SUM(amount), 0) AS balance
FROM credit_transactions
WHERE organisation_id = :org_id;
```

**Invariant:** Balance must never go negative. Enforced at deduction time via:
1. Lock
2. Compute balance
3. Check balance >= amount
4. Insert negative row only if check passes

---

## 4. Authentication & Authorization Flow

```
1. User → Google OAuth
2. Backend receives OAuth token/code
3. Verify with Google, get user info
4. Upsert User (by google_sub), link to Organisation
5. Issue JWT: { sub: user_id, org_id: organisation_id, exp, ... }
6. All API requests: Bearer JWT → extract org_id, user_id
7. All queries scoped by org_id from JWT (never from body)
```

---

## 5. Rate Limiting

- **Scope:** Per `organisation_id`
- **Storage:** Redis (key: `ratelimit:{org_id}:{window}`)
- **Fallback:** On Redis failure, allow request (fail-open) or reject (fail-closed per config)
- **Middleware:** Before route handler, check Redis, increment, enforce limit

---

## 6. Async Jobs (ARQ)

- **Queue:** Redis
- **Worker:** ARQ worker process
- **Job types:** Credit top-up, notifications, cleanup, etc.
- **Idempotency:** Jobs that deduct credits MUST use idempotency keys
- **Failure:** Retry with backoff; dead-letter for permanent failures

---

## 7. Failure Handling

| Failure | Handling |
|---------|-----------|
| **PostgreSQL down** | Connection pool retry; return 503 |
| **Redis down** | Rate limit: configurable fail-open/fail-closed |
| **ARQ/Redis down** | Jobs queued in memory or rejected; no crash |
| **OAuth failure** | Return 401, do not issue JWT |
| **Duplicate idempotency** | Return existing result, 200 OK |
| **Insufficient credits** | Return 402, no ledger change |

---

## 8. Security Checklist

- [ ] JWT signing with strong secret, short expiry
- [ ] Organisation ID from JWT only, never client-supplied for scoping
- [ ] SQL injection: parameterized queries only (SQLAlchemy)
- [ ] CORS configured for allowed origins
- [ ] No sensitive data in logs (mask tokens, PII)

---

## 9. Validation Summary

| Requirement | Status |
|-------------|--------|
| Credit race conditions prevented | ✓ |
| Cross-tenant data leakage prevented | ✓ |
| Duplicate credit deduction prevented | ✓ |
| Inconsistent ledger state prevented | ✓ |
| Layered architecture (api, core, models, schemas, services, middleware, jobs) | ✓ |
| Failure-safe design | ✓ |

**Architect Validator: APPROVED**
