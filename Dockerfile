# syntax=docker/dockerfile:1

# ---------- Stage 1: builder ----------
# Installs dependencies into a virtualenv. Anything else in this stage
# (pip cache, build tooling) is discarded and never reaches the final image.
FROM python:3.12.7-slim-bookworm AS builder

WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy ONLY the dependency manifest first: this layer stays cached until
# requirements.txt changes, even when the source code changes.
COPY app/requirements.txt .
RUN pip install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12.7-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser

# Only the finished virtualenv is copied from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Source code last: it changes most often, so it invalidates the fewest layers.
COPY app/ .

USER appuser
EXPOSE 8000

# Exec form: gunicorn is PID 1 and receives SIGTERM directly (clean shutdown).
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "main:app"]
