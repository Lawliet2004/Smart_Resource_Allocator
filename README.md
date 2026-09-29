# Smart Resource Allocator

A data-driven volunteer coordination platform for NGOs.

NGOs post volunteer tasks (skills, location, time). Volunteers register with
their skills and availability. The system matches them, coordinators approve
applicants, both sides confirm completion.

**Status:** working MVP. Volunteers and coordinators can register, coordinators
post tasks (by hand or by pasting a field report), volunteers browse matched
tasks and apply, and coordinators approve/reject/complete applications. See
[`docs/`](docs/) for the code review notes and the roadmap below for what is
still open.

## Tech stack

- Python 3.11+, FastAPI
- PostgreSQL 16 (via Docker)
- SQLAlchemy 2.0 + Alembic (ORM + migrations)
- pytest (tests), ruff (lint)

## Project layout

```
app/
  core/       # settings, db engine, session factory, logging
  models/     # SQLAlchemy models (one file per table)
  schemas/    # Pydantic request/response models for the JSON API
  services/   # domain logic: skills, scoring, capacity, search, extractor, matcher
  web/        # HTML pages (Jinja + HTMX), auth, CSRF, rate limiting
  api/        # JSON API endpoints
  templates/  # Jinja templates
  static/     # CSS
  main.py     # FastAPI entry point
alembic/
  versions/   # migration scripts
  env.py      # wires Alembic to our models + .env
docs/         # engineering notes
tests/        # pytest suite
requirements.lock  # pinned runtime deps used by the Docker build
docker-compose.yml
pyproject.toml
```

## First-time setup

Prerequisites: Python 3.11+, Docker Desktop, git.

```bash
# 1. Clone and enter
git clone https://github.com/Lawliet2004/Smart_Resource_Allocator.git
cd Smart_Resource_Allocator

# 2. Create local env config
cp .env.example .env

# 3. Virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 4. Install dependencies (editable mode)
pip install -e ".[dev]"

# 5. Start Postgres in Docker
docker compose up -d

# 6. Apply database migrations
alembic upgrade head

# 7. Run the API
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive API.

## Running tests

```bash
pytest
```

Requires Docker Postgres to be running (`docker compose up -d`).

## Common tasks

| Task | Command |
|---|---|
| Start DB | `docker compose up -d` |
| Stop DB (keep data) | `docker compose down` |
| Stop DB + wipe data | `docker compose down -v` |
| New migration | `alembic revision --autogenerate -m "description"` |
| Apply migrations | `alembic upgrade head` |
| Roll back one migration | `alembic downgrade -1` |
| Inspect DB | `docker compose exec db psql -U postgres -d sra` |
| Run tests | `pytest` |
| Lint | `ruff check .` |
| Format | `ruff format .` |

## Current endpoints

Infrastructure:

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe |
| GET | `/health/db` | Readiness probe (checks Postgres) |
| GET | `/docs` | Swagger UI (auto-generated) |
| GET | `/redoc` | ReDoc (auto-generated) |

Auth (HTML):

| Method | Path | Description |
|---|---|---|
| GET/POST | `/register` | Create a volunteer or coordinator account |
| GET/POST | `/login` | Start a session |
| POST | `/logout` | End a session |

Volunteer (`/v`, HTML):

| Method | Path | Description |
|---|---|---|
| GET | `/v/` | Dashboard: top matches (HTMX search), assignments |
| GET/POST | `/v/profile` | Skills, location, availability |
| GET | `/v/tasks` | Matched open tasks, with filters |
| GET | `/v/tasks/{id}` | Task detail |
| POST | `/v/tasks/{id}/apply` | Apply to a task |
| GET | `/v/assignments` | Application history |

Coordinator (`/c`, HTML):

| Method | Path | Description |
|---|---|---|
| GET | `/c/` | Dashboard: tasks, pending applications, analytics |
| GET/POST | `/c/tasks/new` | Create a task |
| GET/POST | `/c/tasks/{id}/edit` | Edit a task |
| POST | `/c/tasks/{id}/status` | Change task status |
| GET | `/c/tasks/{id}/applicants` | Review applicants |
| POST | `/c/assignments/{id}/{approve\|reject\|complete}` | Decide on an application |
| GET/POST | `/c/ingest` | Paste a field report, auto-create a task |

Admin (`/a`, HTML):

| Method | Path | Description |
|---|---|---|
| GET | `/a/` | Users, organizations, system counts |
| POST | `/a/users/{id}/toggle` | Activate / deactivate a user |

JSON API:

| Method | Path | Description |
|---|---|---|
| POST | `/api/ingest/` | Ingest a field report (coordinator session required) |

All unsafe HTML requests require a CSRF token; see "Security notes" below.

## Security notes

- **Sessions:** JWT in an HttpOnly, SameSite=Lax cookie; `Secure` is derived
  from `APP_ENV` unless `SESSION_COOKIE_SECURE` is set explicitly.
- **CSRF:** signed double-submit cookie plus an origin check, enforced for every
  unsafe request by middleware (`app/web/csrf.py`). Templates render the token
  via `{{ csrf_token }}`; HTMX requests may send `X-CSRF-Token` instead.
- **Rate limiting:** slowapi, per IP (or per user for the API). Buckets are
  in-process, so run a single worker or move slowapi to Redis before scaling out.
- **Headers:** CSP, HSTS (deployed envs only), `X-Frame-Options`, `nosniff`,
  `Referrer-Policy`, `Permissions-Policy`.

## Roadmap (high level)

Done:

- Walking skeleton - FastAPI + Postgres + Alembic + tests
- Auth (register, login, session cookie, roles)
- Organizations and Tasks CRUD
- Volunteer profiles (skills, availability, location)
- Rule-based matching and scoring (`app/services/scoring.py`)
- Assignment flow (apply, approve, reject, complete) with capacity limits
- UI (Jinja2 + HTMX), coordinator analytics, field-report ingest
- Deployment artifacts (Docker, compose, CI) and CSRF hardening

Next:

- Distance-based matching (the `latitude` / `longitude` columns are collected
  but not yet used)
- Build Tailwind at release time instead of loading the CDN build, so the CSP
  can drop `unsafe-inline`
- Move skills to an indexed column type so matching filters in the database
- First real NGO pilot

## License

MIT
