ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System dependencies for Playwright + build tooling
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
        wget gnupg ca-certificates \
        fonts-liberation \
        libatk-bridge2.0-0 \
        libcups2 \
        libnss3 \
        libxss1 \
        libasound2 \
        libpangocairo-1.0-0 \
        libgtk-3-0 \
        libxcb-dri3-0 \
        libxdamage1 \
        libgbm1 && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for layer caching
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt -r requirements-dev.txt

# Install Playwright browser binaries + system deps
RUN playwright install chromium && playwright install-deps

# --------------- Runtime image ---------------
FROM base AS runtime

COPY . .

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "-m", "app.main"]

# --------------- Test image ---------------
FROM base AS test

COPY . .

ENV PYTHONPATH=/app \
    ENVIRONMENT=test \
    LOG_LEVEL=INFO \
    ENABLE_HEADLESS_BROWSER=true

CMD ["pytest", "tests_new/", "-v", "--tb=short", "--maxfail=5"]
