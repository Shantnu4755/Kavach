# CLAUDE.md: Kavach

Event-driven insurance claims engine with idempotent APIs, a strict state machine and the transactional outbox pattern. Part of a six-project portfolio platform that runs on one free Oracle ARM VM.

- **Source of truth:** the PDF `~/Downloads/Portfolio Projects Complete Build & Free Deployment Plan.pdf`.
- **Progress and deviations:** `../PROGRESS.md`. Update it after every step. Any change to the PDF's design goes under "Deviations from the plan" with the reason; never change the design silently.

## Rules (PDF "Coding rules")
1. Class-based views only (`BaseView`, a Flask `MethodView`) with **only `get()` and `post()`**. Updates and deletes are a POST to an action endpoint (for example `POST /claims/<id>/approve`). `tests/test_view_rules.py` enforces it.
2. Layers: **View** (HTTP only) → **Service** (business logic) → **Repository** (DB access) → **Model**. A view never writes SQL or opens sessions; a repository never imports Flask.
3. Errors: raise `AppError` subclasses from `app/exceptions.py`. One global handler returns `{"error": {"code", "message", "details", "request_id"}}`. No bare `except:`, no `print`, no swallowed errors (log with `logger.exception` when a loop must continue).
4. Every request is validated with Pydantic (`BaseView.parse_body` / `parse_query`) before it reaches a service.
5. Config from environment variables only (`app/config.py`, fails fast at boot). `.env.example` is committed, `.env` never is.
6. Structured JSON logs with `request_id` on every line. Allowed extra fields: `code`, `error_message`, `job_id`, `service`.
7. pytest for every service class, against real PostgreSQL (never SQLite). External calls (LLM, Telegram, Docker, HTTP) are mocked. CI fails under 80% coverage.

Also: Python 3.12, type hints everywhere, `ruff check .` clean, small commits prefixed `feat:` `fix:` `test:` `docs:` `chore:`. Push after every verified change (the local folder was once deleted by an outside process; GitHub is the backup).

## Layout (PDF 2.1)
`app/{__init__,config,extensions,exceptions,error_handlers,logging_setup}.py`, `app/models`, `app/schemas`, `app/repositories`, `app/services`, `app/views` (`base.py`, `health.py`, `__init__.py` with `register_routes`), `migrations/` (Alembic), `tests/`, `wsgi.py`, `gunicorn.conf.py`, `Dockerfile`, `ui/` (React UI, PDF 3A).

## Commands
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock -r requirements-dev.txt
# local test databases: docker container "portfolio-test-pg" on port 55432 (password "test")
export TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/kavach_test
ruff check . && pytest --cov=app --cov-report=term-missing
DATABASE_URL=... alembic revision --autogenerate -m "describe change" && alembic upgrade head
docker build -t kavach .
```
Dependencies: runtime packages go in `requirements.txt`, test tools in `requirements-dev.txt`. `requirements.lock` is the frozen runtime set (`pip freeze` of a runtime-only install, or of the built image), so pytest never ships in the image.

## Kavach specifics (PDF 3.1)
- **Tables:** `policies` (id, policy_number unique, holder_name, sum_insured Numeric(12,2), is_active, created_at), `claims` (+ `decided_at`), `outbox_events`.
- **Endpoints:** `POST`/`GET /policies`, `GET /policies/<id>`; `POST /claims` (needs `Idempotency-Key` header, max 64 chars; 201 first time, 200 with the same claim on repeat); `GET /claims?status=&q=&sort=&order=&limit=&offset=`; `GET /claims/<id>`; `POST /claims/<id>/approve|reject|pay`; `GET /claims/stats`; `GET /events`.
- **State machine:** SUBMITTED → APPROVED or REJECTED, APPROVED → PAID. Anything else is 409. Status changes take a row lock (`SELECT ... FOR UPDATE`).
- **Outbox:** every change writes an `outbox_events` row in the same transaction. The relay (`python -m app.relay`) loops every 2 s, selects unpublished events `FOR UPDATE SKIP LOCKED`, POSTs each to Karya `POST /jobs` (`KARYA_URL`, idempotency key `kavach:<event id>`) and sets `published_at`. If Karya is down, events wait.
- **Tests to write:** same key twice returns one claim; parallel submissions with one key create one row; PAID → APPROVED is 409; amount above sum insured is 400.
- **UI accent:** emerald (OKLCH hue 162).
