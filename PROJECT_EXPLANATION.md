PROJECT_EXPLANATION.md
What this project is

NexusAPI is a backend system where organisations have credits, and every time they use certain features, credits are deducted. Think of it like a prepaid balance system.

Example:

Organisation buys 100 credits

They use “Analyse text” → 25 credits deducted

They use “Summarise text” → 10 credits deducted

Remaining balance updates automatically

The system ensures:

Credits cannot go below zero

Multiple users cannot cheat the system

Each organisation only sees its own data

System works safely even when many people use it at the same time

High-level system overview (simple analogy)

Think of the system like a bank.

Organisation = Bank account
Credits = Money
CreditTransaction = Bank transaction history
API endpoint = ATM machine
Database = Bank ledger
Backend server = Bank system

Instead of storing balance directly, the system stores transaction history and calculates balance from it.

This prevents errors and fraud.

Technologies used and why

You don’t need coding knowledge to understand this — just see these as tools.

1. FastAPI — backend engine

What it does:

This is the main engine that receives requests and sends responses.

Example:

User clicks “Analyse text” → FastAPI receives request → processes it → sends result

Why used:

Fast

Reliable

Easy to scale

2. PostgreSQL — database (storage)

What it does:

Stores all data safely.

Example data stored:

Organisations

Users

Credit transactions

Jobs

Think of it like a digital spreadsheet but very powerful and safe.

Why used:

Prevents data corruption

Supports locking (important for credit safety)

Used in real production systems

3. SQLAlchemy — database connector

What it does:

Allows backend system to talk to database safely.

Instead of manually writing database commands, SQLAlchemy helps manage data cleanly.

Think of it like a translator between backend and database.

4. Alembic — database version manager

What it does:

Tracks changes in database structure.

Example:

If you add new table, Alembic safely updates database.

Think of it like version control for database.

5. JWT — login authentication

What it does:

Provides secure identity verification.

Example:

User logs in → receives token → token proves identity

Like login session but more secure.

6. Redis / async job system (mock used)

What it does:

Handles background tasks.

Example:

Summarising text happens in background while user continues working.

Like sending email — happens in background.

7. Middleware — system guard layer

Middleware protects system.

Example:

Rate limiting

Error handling

Logging

Think of middleware like security guards and monitoring system.

Step-by-step how system was built (simple explanation)
Step 1: Created basic project structure

Created folders for:

API routes

Database models

Services

Middleware

Tests

This keeps system organized.

Step 2: Setup database connection

Connected backend to database.

Created safe connection system so multiple users can use system without crashes.

Step 3: Created Organisation system

Organisation represents a company using system.

Each organisation is isolated from others.

Example:

Company A cannot see Company B data.

Step 4: Created User system

Users belong to organisations.

Each user has:

email

organisation

role

Roles include:

admin

member

Admin can grant credits.

Step 5: Created CreditTransaction system (core of project)

This is most important part.

Instead of storing balance, system stores transaction history.

Example:

+100 credits
-25 credits
-10 credits

Balance = calculated automatically

This prevents errors.

Step 6: Created credit grant system

Admin can add credits.

Example:

POST /credits/grant

Adds new credit transaction.

Step 7: Created credit balance system

User can check balance.

Example:

GET /credits/balance

System calculates balance safely.

Step 8: Created atomic credit deduction system (most critical part)

When feature is used, credits must be deducted safely.

Problem solved:

If two users try to deduct credits at same time, system prevents double deduction.

Database locking ensures safety.

This prevents fraud or incorrect balance.

Step 9: Created authentication system

Users must log in.

System uses JWT token to identify user safely.

Token proves identity.

Step 10: Created Analyse endpoint

Feature:

User sends text → system analyses text → deducts 25 credits

Example:

POST /api/analyse

System:

checks credits

deducts credits

returns result

Step 11: Created Summarise endpoint (background job)

Feature:

User sends text → system summarises → deducts 10 credits

Job runs in background.

User gets job_id immediately.

Step 12: Created job status endpoint

User can check job status.

Example:

GET /api/jobs/{job_id}

Returns:

pending
completed
failed

Step 13: Created rate limiting system

Prevents abuse.

Limit:

60 requests per minute per organisation

Prevents overload and attacks.

Step 14: Created error handling system

Ensures system never crashes.

Returns safe structured errors.

Example:

Instead of crash, system returns safe message.

Step 15: Created logging system

Tracks system activity.

Helps debugging and monitoring.

How credit safety works (very important concept)

Example scenario:

Organisation has 25 credits.

Two users try to use Analyse feature at same time.

Without protection:

Credits could become -25 (incorrect).

With protection (our system):

Database locks transaction.

Only one request succeeds.

Other fails safely.

This ensures correct balance.

How system prevents cheating

System prevents:

Duplicate requests

Concurrent race conditions

Cross-organisation access

Credit overuse

Using:

Database locking

Idempotency keys

Authentication

Tenant isolation

How async jobs work

Example:

Summarise text.

System:

User sends request
System deducts credits
System creates job
Job runs in background
User checks status

This improves performance.

How system scales

System can support many users because:

Database ensures safety

Backend is async

Jobs run separately

Stateless design allows scaling

Final architecture flow (simple)

User → FastAPI backend → Middleware → Database → Response

Async flow:

User → Backend → Job queue → Worker → Database → Status endpoint

Why system is production-ready

System includes:

Safe credit tracking
Concurrency protection
Authentication
Tenant isolation
Rate limiting
Structured errors
Async jobs
Database migrations

This matches real production backend systems.

Simple real-world analogy

This system is like:

Online prepaid service platform

Organisation buys credits
Uses services
Credits deducted safely
Cannot overspend
System tracks everything

Summary in one paragraph

NexusAPI is a secure backend system that manages organisations, users, and credits. Organisations receive credits and use them to access features like text analysis and summarisation. The system safely tracks credit usage using a transaction ledger, prevents concurrent errors using database locking, protects users with authentication and rate limiting, and supports background jobs. Every part of the system is designed to be safe, scalable, and production-ready.