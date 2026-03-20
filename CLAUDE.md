# CLAUDE.md — datagigbackend

This file provides guidance to Claude Code when working in this repository.

---

## Project Goal

**datagigbackend** is the Python/FastAPI backend service for the DataGigs platform. It is the **sole API gateway for the iOS app** — the iOS app calls ALL operations through this backend, never directly to the website or Supabase. Its responsibilities are:

1. **iOS API gateway** — All iOS GET and POST operations go through this backend. It queries Supabase Postgres directly (via asyncpg) and proxies auth operations to Supabase Auth.
2. **Auth service** — Email OTP send/verify, Apple Sign In token exchange, JWT refresh. All auth connects to the shared Supabase project.
3. **Gigs API** — Serve open gigs and gig detail to the iOS app by querying the shared Supabase Postgres DB directly.
4. **Submission verification** — Download sensor data CSV files from Supabase Storage, evaluate the dataset quality (duration, sample rate, completeness, label correctness), and return a pass/fail result with structured metadata back to the website's Inngest `submission/verify` job.
5. **Email sending API** — Expose endpoints that the website or other services can call to trigger Resend emails.
6. **Future logging/analytics** — Structured logging via `structlog` is configured from day one so a log shipper can be added with zero code changes.

---

## Role

You are a **Senior Python Engineer**, specializing in FastAPI, async Python, and data processing pipelines. Write clean, typed, idiomatic modern Python 3.13. Follow all best practices below precisely.

---

## CLI Commands

**Always use `python3` and `pip3`** — never `python` or `pip`:

```bash
python3 -m venv .venv          # create virtual environment
source .venv/bin/activate       # activate (macOS/Linux)
pip3 install -r requirements.txt
pip3 install <package>

uvicorn app.main:app --reload   # run dev server (port 8000)
python3 -m pytest               # run tests
python3 -m mypy app/            # type check
```

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.13 |
| Web framework | FastAPI >= 0.115 |
| ASGI server | uvicorn[standard] |
| Data validation | Pydantic v2 |
| Config / env vars | pydantic-settings |
| Database (direct async) | asyncpg (same Supabase Postgres as website) |
| Supabase auth / storage | supabase-py (auth JWT verification, Storage downloads) |
| JWT verification | PyJWT[cryptography] |
| Email | Resend Python SDK |
| Dataset evaluation | pandas, numpy |
| Async HTTP client | httpx |
| Logging | structlog |
| Linting / formatting | ruff |
| Testing | pytest + pytest-asyncio + httpx |

**Do not introduce additional third-party packages without asking first.**

---

## Project Structure

```
datagigbackend/
├── .env                        ← secrets (never commit)
├── .env.example                ← committed dummy values
├── pyproject.toml              ← canonical dependency definitions
├── requirements.txt            ← pinned versions for deployment
├── app/
│   ├── __init__.py
│   ├── main.py                 ← FastAPI app factory, lifespan, middleware registration
│   ├── config.py               ← pydantic-settings Settings class (singleton)
│   ├── dependencies.py         ← shared Depends() aliases (auth, db, supabase client)
│   ├── exceptions.py           ← custom exception classes + global handlers
│   ├── logging_config.py       ← structlog configuration (called once at startup)
│   ├── db/
│   │   ├── __init__.py
│   │   └── pool.py             ← asyncpg pool init helpers
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── verify.py           ← POST /verify  (submission verification)
│   │   └── email.py            ← POST /email   (trigger Resend emails)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── verification.py     ← Pydantic request/response models for verify
│   │   └── email.py            ← Pydantic models for email requests
│   └── services/
│       ├── __init__.py
│       ├── verification_service.py  ← dataset download + evaluation logic
│       └── email_service.py         ← Resend email sending logic
└── tests/
    ├── conftest.py
    ├── test_verify.py
    └── test_email.py
```

- Every directory needs `__init__.py`.
- Use relative imports within `app/` (`from ..dependencies import ...`).
- Keep HTTP concerns in `routers/`, business logic in `services/`, data access in `db/`.
- One class/model per file. Never place multiple unrelated types in a single file.

---

## Environment Variables

Store in `.env`. Never commit `.env` — commit `.env.example` with dummy values.

```
# App
APP_ENV=development
SECRET_KEY=changeme

# Supabase (same project as datagigwebsite)
SUPABASE_URL=https://khtxmnskdnvjlxbdscln.supabase.co
SUPABASE_ANON_KEY=<your-supabase-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<your-supabase-service-role-key>

# Database (same Supabase Postgres as datagigwebsite — session mode pooler)
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-us-west-2.pooler.supabase.com:5432/postgres

# Resend
RESEND_API_KEY=<your-resend-api-key>

# Internal auth (shared secret for website → backend calls)
INTERNAL_API_SECRET=changeme
```

### Settings class pattern (always use this)

```python
# app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    resend_api_key: str
    internal_api_secret: str

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

---

## Service Connections

### Supabase — Auth (JWT Verification)

The website and iOS app both issue Supabase JWTs. Verify them using JWKS (asymmetric, preferred):

```python
import httpx
import jwt  # PyJWT[cryptography]

JWKS_URL = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"

async def verify_supabase_jwt(token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(JWKS_URL)
        jwks = resp.json()
    header = jwt.get_unverified_header(token)
    key = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
    return jwt.decode(token, public_key, algorithms=["RS256"], audience="authenticated")
```

Cache the JWKS response (e.g. on `app.state`) — do not fetch it on every request.

### Supabase — Storage (download sensor files)

Sensor data files are uploaded by the iOS app to Supabase Storage bucket `sensor-data`.
Storage path format: `submissions/{userId}/{applicationId}/{gigLabelId}/{timestamp}.csv`

```python
from supabase import create_client

supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

# Download sensor file for verification
file_bytes: bytes = supabase.storage.from_("sensor-data").download(storage_path)
```

Use the **service role key** (not anon key) for server-side storage access — it bypasses RLS.

### Supabase — Database (direct async queries)

Use `asyncpg` for all direct DB queries. The database is the same Supabase Postgres used by the website:

```python
import asyncpg

# In lifespan:
app.state.db_pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=2, max_size=10)

# In dependency:
async def get_db(request: Request):
    async with request.app.state.db_pool.acquire() as conn:
        yield conn
```

Queries use `$1, $2, ...` PostgreSQL positional placeholders (not `%s`).

### Resend — Email

```python
import resend

resend.api_key = settings.resend_api_key

# Send email
params: resend.Emails.SendParams = {
    "from": "DataGigs <noreply@datagigs.com>",
    "to": ["user@example.com"],
    "subject": "Subject here",
    "html": "<p>Body here</p>",
}
email = resend.Emails.send(params)
```

- Production sender: `DataGigs <noreply@datagigs.com>`
- Dev/test: only delivers to the Resend account owner's email (`onboarding@resend.dev` as sender if needed for testing)
- The website (datagigwebsite) handles most emails (application accept/deny, payout). This backend handles verification-specific emails only.

---

## API Design

### App factory + lifespan

```python
# app/main.py
from contextlib import asynccontextmanager
import asyncpg
from fastapi import FastAPI
from app.config import settings
from app.logging_config import configure_logging
from app.routers import verify, email as email_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.db_pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=2, max_size=10)
    yield
    await app.state.db_pool.close()

app = FastAPI(title="DataGigs Backend", lifespan=lifespan)
app.include_router(verify.router)
app.include_router(email_router.router)
```

### All routes

#### Public (no auth required)
| Method | Path | Caller | Purpose |
|---|---|---|---|
| `GET` | `/health` | Any | Health check |
| `POST` | `/auth/otp/send` | iOS | Send 6-digit OTP to email via Supabase |
| `POST` | `/auth/otp/verify` | iOS | Verify OTP code, return JWT + refresh token |
| `POST` | `/auth/apple` | iOS | Exchange Apple identity token for Supabase session |
| `POST` | `/auth/refresh` | iOS | Refresh expired JWT using refresh token |
| `GET` | `/gigs` | iOS | List open gigs (queries Supabase DB directly) |
| `GET` | `/gigs/{id}` | iOS | Gig detail with labels + device requirements |

#### Authenticated (Bearer token required — iOS user)
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/applications` | Submit application to a gig |
| `GET` | `/applications` | List current user's applications |
| `GET` | `/applications/{id}` | Single application detail with gig labels |
| `GET` | `/profile` | User dashboard stats (display name, credits balance) |

#### Internal secret (website → backend)
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/verify` | Submission verification (called by website Inngest job) |
| `POST` | `/email/send` | Trigger a Resend email |

### Auth endpoint contracts

#### POST /auth/otp/send
```json
Request:  { "email": "user@example.com" }
Response: { "message": "OTP sent" }
```
Backend calls: `supabase.auth.sign_in_with_otp(email=email)`
Supabase sends a 6-digit code to the user's email.

#### POST /auth/otp/verify
```json
Request:  { "email": "user@example.com", "token": "482917" }
Response: { "access_token": "...", "refresh_token": "...", "user_id": "uuid" }
```
Backend calls: `supabase.auth.verify_otp(email=email, token=token, type="email")`
On first sign-in, also creates `users` + `user_profiles` rows in DB (role always `user` for iOS).

#### POST /auth/apple
```json
Request:  { "identity_token": "<Apple JWT string>" }
Response: { "access_token": "...", "refresh_token": "...", "user_id": "uuid" }
```
Backend calls: `supabase.auth.sign_in_with_id_token(provider="apple", id_token=identity_token)`
On first sign-in, also creates `users` + `user_profiles` rows if not present.

#### POST /auth/refresh
```json
Request:  { "refresh_token": "..." }
Response: { "access_token": "...", "refresh_token": "..." }
```
Backend calls: `supabase.auth.refresh_session(refresh_token=refresh_token)`

### Gigs endpoint contracts

#### GET /gigs
Query params: `page` (default 1), `limit` (default 20, max 50)
```json
Response: [
  {
    "id": "uuid",
    "title": "Horse riding sensor data",
    "description": "...",
    "activity_type": "horse_riding",
    "status": "open",
    "total_slots": 20,
    "filled_slots": 4,
    "application_deadline": "2026-04-01T00:00:00Z",
    "data_deadline": "2026-04-15T00:00:00Z",
    "company_name": "Equine Research Co",
    "min_rate_cents": 500,
    "max_rate_cents": 1000,
    "device_types": ["generic_ios", "apple_watch"]
  }
]
```
Query: SELECT from `gigs` WHERE status = 'open', JOIN `company_profiles` for company_name, JOIN `gig_labels` for min/max rate, JOIN `gig_device_requirements` for device_types.

#### GET /gigs/{id}
```json
Response: {
  "id": "uuid",
  "title": "...",
  "description": "...",
  "activity_type": "...",
  "status": "open",
  "total_slots": 20,
  "filled_slots": 4,
  "application_deadline": "...",
  "data_deadline": "...",
  "company_name": "...",
  "labels": [
    {
      "id": "uuid",
      "label_name": "walking on horse",
      "description": "...",
      "duration_seconds": 120,
      "rate_cents": 500,
      "quantity_needed": 20,
      "quantity_fulfilled": 4
    }
  ],
  "device_types": ["generic_ios"]
}
```

### Internal auth (website → backend calls)

Routes called by the website use a shared `INTERNAL_API_SECRET` header, not a user JWT:

```python
from fastapi import Header, HTTPException, Depends
from typing import Annotated

async def require_internal(x_internal_secret: Annotated[str, Header()]) -> None:
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

InternalAuth = Annotated[None, Depends(require_internal)]
```

---

### Applications endpoint contracts

#### POST /applications
Auth: Bearer token
```json
Request:  { "gig_id": "uuid", "device_type": "generic_ios|apple_watch|generic_android", "note_from_user": "optional, max 500 chars" }
Response: { "id": "uuid", "gig_id": "uuid", "status": "pending", "applied_at": "ISO8601" }
```
Validation: gig must be open + have slots, device_type must be in gig_device_requirements, no duplicate application (unique gig_id+user_id).

#### GET /applications
Auth: Bearer token
```json
Response: [
  { "id": "uuid", "gig_id": "uuid", "gig_title": "...", "status": "pending|accepted|denied|withdrawn",
    "device_type": "generic_ios", "assignment_code": "ABC123DEF456" | null,
    "applied_at": "ISO8601", "note_from_company": "..." | null }
]
```

#### GET /applications/{id}
Auth: Bearer token. Returns 404 if application doesn't belong to current user.
```json
Response: {
  ...same as list item,
  "note_from_user": "..." | null,
  "gig_detail": {
    "title": "...", "description": "...", "activity_type": "...", "data_deadline": "ISO8601" | null,
    "labels": [ { "id": "uuid", "label_name": "...", "duration_seconds": 120, "rate_cents": 500 } ]
  }
}
```

#### GET /profile
Auth: Bearer token
```json
Response: { "display_name": "Natalya", "credits_balance_cents": 2450 }
```

---

## Submission Verification

The website's Inngest `submission/verify` job calls `POST /verify` with:

```json
{
  "submissionId": "uuid",
  "storagePath": "submissions/{userId}/{applicationId}/{gigLabelId}/{timestamp}.csv",
  "gigLabelId": "uuid",
  "durationSeconds": 120,
  "deviceType": "generic_ios"
}
```

The backend should:
1. Download the CSV from Supabase Storage (`sensor-data` bucket)
2. Parse with pandas
3. Evaluate: duration matches, sample rate is adequate, no corrupt rows, etc.
4. Return:
```json
{
  "passed": true,
  "result": {
    "actual_duration_seconds": 121.4,
    "sample_count": 6070,
    "sample_rate_hz": 50.0,
    "issues": []
  }
}
```

The website's Inngest job uses this response to set `submissions.verification_result` (jsonb) and `submissions.status`.

---

## Python Best Practices

### Type hints — always

```python
# Every function signature must be fully annotated
async def verify_submission(storage_path: str, duration_seconds: int) -> VerificationResult:
    ...

# Use X | None over Optional[X] (Python 3.10+)
# Use list[str] over List[str] (Python 3.9+)
```

Run `mypy` or `pyright` to enforce. Never leave unannotated functions.

### Async patterns

- `async def` for all endpoints and any function doing I/O (DB, HTTP, file reads).
- `def` only for pure CPU-bound logic (FastAPI runs these in a thread pool).
- Never call blocking code inside `async def` — use `asyncio.to_thread()` for CPU-heavy pandas work if needed.
- Never use `time.sleep()` — use `await asyncio.sleep()`.
- Never use `requests` — use `httpx.AsyncClient`.

### Pydantic v2 models

```python
from pydantic import BaseModel, Field, ConfigDict

class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str = Field(..., description="UUID of the submission")
    storage_path: str
    duration_seconds: int
    device_type: str

class VerifyResponse(BaseModel):
    passed: bool
    result: dict
```

- `extra="forbid"` on all request models — reject unknown fields.
- `from_attributes=True` on response models that are built from asyncpg Records.
- Use `model_dump(exclude={"sensitive_field"})` when returning data.

### Error handling

```python
# app/exceptions.py
class AppError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code

class NotFoundError(AppError):
    def __init__(self, resource: str):
        super().__init__(f"{resource} not found", status_code=404)
```

- Raise `AppError` subclasses from services — never `HTTPException` from the service layer.
- Register a global handler in `main.py` that converts `AppError` to JSON responses.
- Never expose stack traces in API responses — log them with structlog.

### Logging

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info("submission_verified", submission_id=sub_id, passed=True, duration=121.4)
logger.error("storage_download_failed", storage_path=path, error=str(e))
```

- Always log with key=value pairs, never f-strings.
- Bind `request_id` per request via middleware so all logs for a request share the same ID.

### General rules

- Use `pathlib.Path` over `os.path`.
- Use `|` union syntax, not `Optional[T]` or `Union[T, None]`.
- Never use `import *`.
- Prefer `@dataclass` for internal DTOs (no validation overhead); Pydantic only for HTTP boundaries.
- Use `ruff` for linting and formatting — it replaces flake8, black, and isort.

---

## Dependency Management

Use **both** `pyproject.toml` (source of truth) and `requirements.txt` (pinned, for deployment):

```toml
# pyproject.toml
[project]
name = "datagigbackend"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "asyncpg>=0.30",
    "supabase>=2.0",
    "PyJWT[cryptography]>=2.8",
    "httpx>=0.27",
    "structlog>=24.0",
    "resend>=2.0",
    "pandas>=2.0",
    "numpy>=2.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["mypy", "pytest", "pytest-asyncio", "ruff"]
```

Generate pinned `requirements.txt`:
```bash
pip3 freeze > requirements.txt
```

---

## Testing

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- Use `pytest-asyncio` with `asyncio_mode = "auto"` in `pyproject.toml`.
- Test services with unit tests (mock storage/DB calls).
- Test routers with `httpx.AsyncClient` against the ASGI app — no running server needed.
- Never test with real Supabase/Resend in CI — mock external calls.

---

## Important Rules

- **No git commits** — only the human makes commits.
- **Credentials alert** — if any code, config, or file you write or encounter contains credentials, passwords, API keys, or tokens, immediately alert the user and add a `# credentials` comment on the line immediately after.
- **Always `python3` and `pip3`** — never `python` or `pip`.
- **Never commit `.env`** — only `.env.example`.
- **All monetary values** from the shared database are in cents (integers).
- **Storage bucket** is `sensor-data` in Supabase project `khtxmnskdnvjlxbdscln`.
- When the master agent (orchestrator) updates the API contract between website and backend, this CLAUDE.md will be updated — always re-read before changing the `/verify` endpoint schema.
- The website is the source of truth for the database schema — do not run Prisma migrations from this repo. Read-only DB access is fine; write only to update `submissions.verification_result` and `submissions.status` if doing so directly (or let the website do it via the verify response).
