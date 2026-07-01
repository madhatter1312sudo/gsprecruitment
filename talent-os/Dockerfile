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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]