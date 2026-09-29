# Code review — Smart Resource Allocator

Reviewed at commit `aa27b39` ("feat: redesign volunteer dashboard with HTMX search and CSS charts").

> **Status:** items 1.1-1.5, 2.1-2.4, 2.6, the matcher ranking, the extractor
> output guard, the test-suite items and most of the repo hygiene list were
> addressed in the follow-up commit on this branch. Each heading below is marked
> **[fixed]** or **[open]**. The remaining open items are the bigger structural
> ones (ORM relationships, indexed skill columns, building Tailwind at release
> time, Redis-backed rate limits).

Overall this is a well-structured small FastAPI app: clean layering (`core` / `models` /
`services` / `web` / `api`), thoughtful security work already in place (timing-equalized
login, security headers, rate limiting, open-redirect guards on `next`, configurable
query limits, sanitized 500s). The items below are what I'd fix next, roughly in priority
order.

---

## 1. Blocking / correctness

### 1.1 CI lint is red on `main` — **[fixed]**
`ruff check .` currently fails:

```
I001 Import block is un-sorted or un-formatted
 --> tests/test_dashboard_search.py:1:1
```

The last commit added `tests/test_dashboard_search.py` with unsorted imports, and the
`test` job `needs: lint`, so the whole pipeline is failing. One-line fix:
`ruff check --fix tests/test_dashboard_search.py`.

### 1.2 No CSRF protection on any state-changing POST — **[fixed]**
There is no CSRF token anywhere in the app (`grep -i csrf` returns nothing). Every
mutating route is a cookie-authenticated `POST` form: `/login`, `/register`, `/logout`,
`/v/profile`, `/v/tasks/{id}/apply`, `/c/tasks/new`, `/c/tasks/{id}/edit`,
`/c/tasks/{id}/status`, `/c/assignments/{id}/{action}`, `/a/users/{id}/toggle`.

`SameSite=Lax` blocks the classic cross-site form POST in current browsers, which is why
this hasn't bitten yet — but it's the only thing standing between an attacker and
"admin deactivates a user" or "coordinator approves an applicant" via a cross-origin
request. For an app that is about to be piloted with a real NGO, add a signed
double-submit token: one helper that injects `{{ csrf_input() }}` into every form +
one dependency/middleware that validates it on unsafe methods. Also worth adding a
strict `Origin`/`Referer` check as defence in depth, since `form-action 'self'` in the
CSP does not protect the *target*.

### 1.3 The dashboard HTMX search points at the wrong URL — **[fixed]**
`app/templates/volunteer/dashboard.html`:

```html
hx-get="/"
```

`/` is the auth index route, which 303-redirects to `/v/`. HTMX follows the redirect so
the feature "works", but every keystroke costs two requests plus a DB lookup, and it
breaks the moment the index route changes. It should be `hx-get="/v/"`.

Related: the input is not wrapped in a form and doesn't push the URL, so the search term
is lost on refresh (`hx-push-url="true"` would fix that cheaply).

### 1.4 `GEMINI_API_KEY` never reaches the production container — **[fixed]**
`docker-compose.prod.yml` passes `DATABASE_URL`, `JWT_SECRET`, `APP_ENV`,
`SESSION_COOKIE_SECURE`, `TRUST_FORWARDED_HEADERS` — but not `GEMINI_API_KEY`. Deploy as
documented in `DEPLOY.md` and the LLM extractor silently degrades to `_mock_extract()`
with no warning. Add the variable (and mention it in `DEPLOY.md`).

Mirror-image problem in `.env.example`:

```
GEMINI_API_KEY="gemini_api_key_goes_here"
```

That placeholder is *truthy*, so a fresh `cp .env.example .env` makes every ingest attempt
a real API call, fail, log a full traceback, and fall back. Ship it empty
(`GEMINI_API_KEY=`) so the "not configured" path is the default.

### 1.5 `docker-compose.prod.yml` never runs migrations — **[fixed]**
The app container starts uvicorn directly; `DEPLOY.md` tells you to run
`alembic upgrade head` manually afterwards. That means the first boot of a fresh stack
serves 500s against an empty schema. Either add an entrypoint that runs
`alembic upgrade head && exec uvicorn ...`, or a one-shot `migrate` service that `app`
depends on.

---

## 2. Correctness / consistency bugs

### 2.1 Dashboard search and task-page search behave differently — **[fixed]**
- `matched_open_tasks(..., q=...)` filters in SQL on `Task.title.ilike(...)` only.
- `filter_matched_tasks()` (used by `/v/tasks`) filters in Python on title **and**
  description.

Same-looking search box, different results. Pick one behaviour (ideally the SQL one,
extended to `description`) and share it.

### 2.2 `q` is unvalidated on `/v/` but validated on `/v/tasks` — **[fixed]**
`/v/tasks` rejects `q` over `MAX_TASK_SEARCH_CHARS`; the dashboard route takes
`q: str | None = None` straight into an `ILIKE`. Apply the same cap.

Also, `%` and `_` in `q` are not escaped, so `q=%` matches everything and `q=%%%%%...`
is a cheap way to make Postgres work harder than it should. Escape them and use
`.ilike(pattern, escape="\\")`.

### 2.3 Capacity/approval races are unguarded — **[fixed]**
`apply_to_task` and `decide_assignment` both do read-then-write on capacity:

```python
capacity = capacity_summary(task, filled_slots_for_task(db, task.id))
if capacity["is_full"]: ...
assignment.status = "approved"
db.commit()
```

Two coordinators approving concurrently can both pass the check and overfill the task.
`SELECT ... FOR UPDATE` on the task row (or a conditional `UPDATE ... WHERE` on the
count) closes it. Low probability today, but it's silent data corruption when it happens.

### 2.4 Silent failure in `apply_to_task` — **[fixed]**
```python
except IntegrityError:
    db.rollback()
return RedirectResponse(f"...?message=Application submitted.")
```
On a unique-constraint clash the user is told the application was submitted even though
nothing was written. Return the "already applied" message instead.

### 2.5 `get_or_create_*` on GET requests — **[open]**
`get_or_create_profile` / `get_or_create_organization` write to the DB from idempotent
GET handlers (including every dashboard render). It works, but it means read-only pages
can fail on a read replica or a locked DB, and it makes the `/v/` route non-cacheable in
principle. Creating these rows at registration (which `auth.register` already does) and
treating a missing row as an error state would be cleaner.

### 2.6 Cross-import from `api` into `web` — **[fixed]**
`app/api/endpoints/ingest.py` does a function-local
`from app.web.coordinator import normalize_skills`. Skill normalisation is business
logic — it belongs in `app/services/` (next to `SKILL_OPTIONS`), imported by both
layers. Same for the duplicated `normalize_skills` in `web/volunteer.py` and
`web/coordinator.py`, which are byte-identical.

---

## 3. Data model & performance

- **No ORM relationships.** None of the five models declare `relationship()`, so every
  page joins by hand and returns tuples like `(assignment, task, volunteer)` into the
  templates. Adding relationships + `selectinload` would simplify the query code a lot.
- **`required_skills` / `skills` as JSON columns.** Skill filtering is therefore done in
  Python after pulling up to `VOLUNTEER_TASK_SCAN_LIMIT` (500) rows. On Postgres,
  `ARRAY(String)` or `JSONB` with a GIN index would let the database do it — worth doing
  before the pilot if task volume grows.
- **`find_best_volunteers` scans and filters in Python** the same way, capped at 500
  candidates ordered by `id DESC`, which silently drops matches once you have more than
  500 available volunteers. The cap should at minimum be applied *after* filtering.
- **The matcher returns an unranked list** despite the name "best" — no scoring, no
  ordering, while `volunteer.task_match_score` implements exactly that logic for the
  other direction. One shared scoring function would fix both.
- **Missing index:** `tasks.urgency` is used for `ORDER BY urgency DESC, id DESC` on the
  hot volunteer path. Check `c8a73d17f0b2_add_query_performance_indexes` covers it.
- **`latitude`/`longitude` are collected on both models and never used.** Leaflet is
  loaded on every page from a CDN for the same reason. Either implement the haversine
  distance ranking the README promises for Week 5, or drop the dead weight.

---

## 4. Security hardening (beyond CSRF)

- **No session revocation.** A stateless JWT in a cookie means deactivating a user in the
  admin panel doesn't kick them out... actually it does, because `get_current_user`
  re-checks `is_active` on every request — good. But "log out everywhere" and password
  change invalidation are impossible; a `token_version` column on `User` would give you
  that for ~10 lines.
- **CSP allows `'unsafe-inline'` scripts and two CDNs.** That is forced by
  `cdn.tailwindcss.com` (which compiles Tailwind in the browser and is explicitly not for
  production). Building CSS at release time into `app/static/css` would let you drop
  `'unsafe-inline'` *and* `cdn.tailwindcss.com` from the CSP, remove a third-party
  dependency from the critical path, and speed up first paint.
- **Unpinned CDN dependencies** — `htmx.org@1.9.12` and Leaflet are loaded without SRI
  hashes. Add `integrity`/`crossorigin` or vendor them.
- **Rate limiter is in-process memory.** With more than one uvicorn worker, the limits are
  effectively multiplied by the worker count. Point slowapi at Redis for the pilot, or
  document the single-worker constraint.
- **No rate limit on the expensive authenticated paths** (`/v/`, `/c/` dashboards run
  several aggregate queries each; `/health/db` hits the DB unauthenticated).
- **Passwords:** minimum length 8 with no other checks and no breach-list lookup. Also
  `bcrypt<4.1` is pinned to dodge a passlib incompatibility — passlib is unmaintained;
  moving to `pwdlib`/`argon2-cid` or calling `bcrypt` directly removes a dead dependency.
- **Error messages are passed through the query string** (`?error=Task not found.`) and
  rendered into the page. Jinja autoescaping means it's not XSS, but any attacker can
  craft a link that makes your app display arbitrary text to the victim ("Your account
  was compromised, call this number"). Use short error *codes* mapped to messages
  server-side.

---

## 5. Tests

23 tests, all integration-style against a live Postgres. Gaps:

- **No unit tests for the interesting logic**: `task_match_score`, `find_best_volunteers`,
  `_mock_extract`, `capacity_summary` edge cases. These are pure functions — they should
  be tested without a database.
- **`tests/test_dashboard_search.py` imports `_reset_web_tables` from `tests/test_web.py`**
  — a private helper from a sibling test module. Move it into `conftest.py` as a fixture;
  better still, make it an `autouse` fixture so each test starts clean instead of each
  test remembering to call it.
- **No coverage measurement** in CI, and no `pytest-cov` in the dev extras.
- **Tests share one `TestClient`/app instance with the real settings object**, so anything
  that depends on `APP_ENV` (HSTS, cookie `Secure`) can only be tested in the one
  configuration CI happens to run.
- **The Gemini path is never exercised** — `extract_task_data` with a key set is untested;
  a mocked `genai.Client` test would catch schema drift.

---

## 6. Repo hygiene / DX

- `README.md` says "See `/docs` for roadmap" — there is no `docs/` directory (this file is
  the first one). The roadmap in the README also says "Week 1 (current)" while the code is
  clearly at Week 7+; and the "Current endpoints" table lists only the four health/docs
  routes, none of the ~20 web routes that exist.
- **No dependency lock file.** `pyproject.toml` uses floors only (`fastapi>=0.115`), so CI
  and production can resolve to different versions than the developer's machine. A
  `requirements.lock` / `uv.lock` / `pip-compile` output makes builds reproducible — and
  the Dockerfile currently reinstalls the world on any source change because it copies
  `app/` *before* installing.
- **Dockerfile layer ordering:** `COPY app ./app` happens before `pip install .`, so every
  code edit busts the dependency layer. Install deps from a lock file first, copy source
  last.
- **No healthcheck for the `db` dependency at startup** — the app will crash-loop on a
  cold `docker compose up` until Postgres is ready (the prod compose does handle this
  with `condition: service_healthy`; the dev one doesn't matter as much).
- **CI doesn't run `ruff format --check`**, so formatting drifts (there is trailing
  whitespace in `app/web/volunteer.py` and `app/services/extractor.py` today).
- **No type checking.** The codebase already annotates nearly everything; adding `mypy` or
  `pyright` to the dev extras and CI is nearly free and would have caught, e.g.,
  `require_volunteer` returning `User | RedirectResponse` being used as a `User`.
- **`logging` is never configured** — `logger.exception` output depends entirely on
  uvicorn's default handler. A small `logging.config.dictConfig` in `main.py` (JSON in
  prod) would make the pilot debuggable.
- **No `/metrics`, no request IDs, no Sentry.** For a real deployment, a request-ID
  middleware echoed into logs is the cheapest observability win.
- `app/schemas/task.py` and `app/schemas/volunteer.py` exist — check they're still used
  now that the web layer renders ORM objects directly.

---

## Suggested order of attack

1. Fix the red CI lint (1.1) — 1 minute.
2. `hx-get="/v/"`, `q` validation + `%`/`_` escaping, `GEMINI_API_KEY` in prod compose,
   empty placeholder in `.env.example` (1.3, 1.4, 2.2) — under an hour.
3. CSRF tokens on all forms (1.2) — half a day, highest security value.
4. Extract shared `normalize_skills` + a single scoring function into `app/services/`,
   add unit tests for them (2.6, §5) — half a day.
5. Migrations on deploy + a dependency lock file + Dockerfile layer fix (1.5, §6) — half a
   day, makes the pilot deployment repeatable.
6. Then the bigger items: build Tailwind at release time (drops `'unsafe-inline'`), ORM
   relationships, JSONB/array skills with a real index, row locking on capacity.

---

## Changes made in the follow-up commit

| Area | Change |
|---|---|
| CI | Fixed the `I001` failure that was blocking the whole pipeline |
| CSRF | New `app/web/csrf.py`: signed double-submit cookie + origin check, enforced for every unsafe request by ASGI middleware; hidden token rendered into all 15 forms |
| Search | Unified on one SQL search over title + description; wildcards escaped via `app/services/search.py`; `q` clamped on both entry points; `hx-get="/v/"` with `hx-push-url` |
| Domain logic | New `app/services/skills.py` (one skill vocabulary, one `normalize_skills`) and `app/services/scoring.py` (one eligibility rule + one score, shared by the volunteer list and the matcher) |
| Matcher | Now ranks by score and applies the candidate cap after filtering instead of dropping matches by id |
| Extractor | `sanitize_extraction()` clamps model-authored title/location/urgency/people_needed and normalizes skills, so a bad LLM response cannot break the Task insert |
| Concurrency | `lock_task_for_update()` (`SELECT ... FOR UPDATE`) wraps the capacity check in both the apply and approve paths |
| Honesty | Duplicate applications now report "already submitted" instead of a phantom success |
| Deploy | `GEMINI_API_KEY` + `RUN_MIGRATIONS` in prod compose; `docker-entrypoint.sh` runs migrations before serving; `requirements.lock` + reordered Dockerfile layers; empty `GEMINI_API_KEY` placeholder in `.env.example` |
| Observability | `app/core/logging.py` with an explicit `dictConfig` |
| Tests | 23 → 58. `conftest.py` owns the DB reset (autouse) and a CSRF-aware client; new `test_csrf.py` (10) and `test_services.py` (22, no DB) |
| Docs | README status/layout/endpoints/roadmap corrected, security notes added; DEPLOY.md documents the API key, migrations and CSRF |

### Still open (deliberately)

- ORM `relationship()`s and `selectinload` instead of manual joins returning tuples
- `skills` / `required_skills` as indexed `ARRAY`/`JSONB` so matching filters in SQL
- Build Tailwind at release time to drop `'unsafe-inline'` and the CDN from the CSP;
  add SRI to the remaining CDN scripts
- Redis-backed rate limiting (in-process buckets multiply per worker)
- Error *codes* in query strings instead of attacker-controllable error text
- `token_version` on `User` for "log out everywhere"
- `get_or_create_*` writing from GET handlers
- mypy/pyright and `ruff format --check` in CI (the latter needs a formatting pass first)
- Haversine distance ranking using the unused `latitude` / `longitude` columns
