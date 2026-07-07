# Talent OS — Dockerfile
# Multi-stage: builder → runtime (minimal image)
# ── Builder ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Runtime ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Install PostgreSQL client for backup scripts
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/local /usr/local

# Copy application code
COPY . .

# Run as non-root user
RUN useradd -m -u 1000 talentos && chown -R talentos:talentos /app
USER talentos

EXPOSE 8000

# --forwarded-allow-ips=* trusts X-Forwarded-For from whatever connects to
# uvicorn directly. Safe here specifically because docker-compose.yml binds
# this container's port to 127.0.0.1 only -- the sole thing that can ever
# connect is the trusted local Caddy reverse proxy, never the public
# internet. Without this, slowapi's rate limiter keys on the Docker bridge
# gateway IP for every request (since that's the apparent peer, not the
# real client), making every rate limit a single shared global bucket
# instead of per-client -- trivially enabling one bad actor to lock out
# all users from login/register/password-reset.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", \
     "--proxy-headers", "--forwarded-allow-ips=*"]