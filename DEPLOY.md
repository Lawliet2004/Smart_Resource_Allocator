# Deployment Guide (Track A)

This document prepares Smart Resource Allocator for production-style deployment. It does not perform deployment automatically.

## Required environment variables

Set these variables in your deployment platform or shell:

- DATABASE_URL: PostgreSQL DSN, for example `postgresql+psycopg://postgres:strongpassword@db:5432/sra`
- JWT_SECRET: a random secret string with at least 32 characters
- APP_ENV: `production` (or `prod` / `staging`)
- SESSION_COOKIE_SECURE: `true`

Optional tuning variables:

- AUTH_LOGIN_RATE_LIMIT (default: `10/minute`)
- AUTH_REGISTER_RATE_LIMIT (default: `5/minute`)
- INGEST_RATE_LIMIT (default: `30/minute`)
- TRUST_FORWARDED_HEADERS (default: `false`) — set to `true` **only** when the app runs behind a trusted reverse proxy (Caddy, nginx, Fly proxy, Cloudflare Tunnel, etc.) that overwrites `X-Forwarded-For`. Leaving it `false` when directly exposed prevents clients from spoofing the header to bypass rate limits.

## Build and run with Docker Compose (production file)

1. Build and start services:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

2. Run DB migrations in the app container:

```bash
docker compose -f docker-compose.prod.yml exec app alembic upgrade head
```

3. Check health endpoint:

```bash
curl http://localhost:8000/health
```

4. Stop services:

```bash
docker compose -f docker-compose.prod.yml down
```

## Build and run image directly

1. Build image:

```bash
docker build -t smart-resource-allocator:latest .
```

2. Run container:

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql+psycopg://postgres:strongpassword@host.docker.internal:5432/sra" \
  -e JWT_SECRET="replace-with-a-32-plus-char-secret" \
  -e APP_ENV="production" \
  -e SESSION_COOKIE_SECURE="true" \
  smart-resource-allocator:latest
```

## HTTPS requirement

Terminate HTTPS at a reverse proxy (for example Caddy, nginx, or Fly proxy) in front of the app container. The app expects secure traffic handling at the edge in production.

## Database backup and restore

Backup (host command):

```bash
pg_dump "$DATABASE_URL" > sra_backup.sql
```

Restore (host command):

```bash
pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" sra_backup.sql
```
