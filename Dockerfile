FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install pinned dependencies first, in their own layer: editing application
# code must not invalidate the (slow) dependency install.
COPY requirements.lock ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock

# Then add the application itself, without re-resolving dependencies.
COPY pyproject.toml README.md ./
COPY app ./app
RUN /opt/venv/bin/pip install --no-cache-dir --no-deps .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --home /home/appuser appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

USER appuser

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
# Use shell form so ${PORT} expands at runtime. Hosts like Render / Fly /
# Railway inject a PORT env var the app must bind to; fall back to 8000 for
# local docker compose runs where no PORT is set.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
