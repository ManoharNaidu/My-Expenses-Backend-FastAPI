# My Expenses API

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Uvicorn](https://img.shields.io/badge/Uvicorn-ASGI-009688)](https://www.uvicorn.org)

FastAPI backend for the My Expenses Flutter app.

## What this service does

- Authenticates users and issues JWT tokens.
- Stores and updates transactions, budgets, settings, onboarding state, and staged upload data.
- Handles bank PDF upload and staged transaction review flows.
- Sends verification and password reset email codes.
- Runs health, feedback, debt, budget, and weekly digest workflows.

## Runtime environments

| Environment | Purpose |
|---|---|
| Python 3.12 | Backend runtime |
| `.venv` | Isolated virtual environment for backend dependencies |
| `.env` | Local environment configuration for required secrets and service URLs |

There is no Flutter virtual environment in this folder. Flutter is run separately from the `my_expenses/` directory.

### Fast path

| Task | Command |
|---|---|
| Activate env | `.\.venv\Scripts\Activate.ps1` |
| Install deps | `pip install -r requirements.txt` |
| Run server | `uvicorn main:app --reload --host 0.0.0.0 --port 8000` |
| Syntax check | `python -m compileall -q main.py pdf_parser.py core routes schemas services` |

## Prerequisites

- Python 3.12
- `pip`
- A valid Supabase project
- Brevo email API credentials
- A JWT secret

## Required environment variables

Create `My Expenses API/.env` and provide these values:

- `JWT_SECRET`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `BREVO_API_KEY`
- `SENDER_EMAIL`

Optional variables:

- `SENDER_NAME`
- `JWT_EXPIRE_MINUTES`
- `PORT`
- `MAX_UPLOAD_BYTES`
- `WEEKLY_DIGEST_CRON_TOKEN`

Example:

```bash
JWT_SECRET=your-very-long-secret
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
BREVO_API_KEY=your-brevo-api-key
SENDER_EMAIL=no-reply@example.com
SENDER_NAME=My Expenses
PORT=8000
```

## Create and activate the virtual environment

From `My Expenses API/`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you want to run tests locally, install `pytest` into the same virtual environment:

```powershell
pip install pytest
```

## Run the backend

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API is mounted under `/api/v1` for app routes, and `/health` is available as a basic health check.

## Quick validation commands

```powershell
python -m compileall -q main.py pdf_parser.py core routes schemas services
```

If pytest is installed:

```powershell
pytest tests
```

## Project layout

- `main.py` app entry point and router registration.
- `core/` configuration, security, database, email, and OTP helpers.
- `routes/` FastAPI route handlers.
- `schemas/` request and response models.
- `models/` data representations used by the app.
- `services/` business workflows such as weekly digest.
- `migrations/` SQL migrations.
- `tests/` backend test suite.

## Development notes

- Keep secrets out of source control.
- Use new timestamped SQL files for database changes.
- Backend config is strict: missing required env vars fail fast on startup.
- The test suite is intended to run offline with mocked Supabase dependencies.

## Suggested documentation style

- Start with the purpose of the service, then move into setup.
- Put environment variables in a compact list or table.
- Keep commands grouped by task: setup, run, validate.
- Keep the file short enough that a new contributor can scan it in under a minute.
