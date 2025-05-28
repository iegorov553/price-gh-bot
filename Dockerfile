# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ---- Playwright system deps & browser binaries ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget gnupg ca-certificates \
        fonts-liberation libatk-bridge2.0-0 libcups2 libnss3 libxss1 \
        libasound2 libpangocairo-1.0-0 libgtk-3-0 libxcb-dri3-0 \
        libxdamage1 libgbm1 && \
    rm -rf /var/lib/apt/lists/*

# Download only Chromium browsers and verify installation
RUN playwright install chromium
RUN playwright install-deps

# Verify browsers are installed correctly
RUN python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print('Chromium path:', p.chromium.executable_path); p.stop()"

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "app.main"]