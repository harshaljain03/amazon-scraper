# Multi-stage build for Amazon Scraper with Playwright, proxies, DB, and monitoring
FROM python:3.11-slim as base

# Switch to a more reliable Debian mirror (robust for slim images)
RUN (test -f /etc/apt/sources.list && sed -i 's|http://deb.debian.org/debian|http://ftp.us.debian.org/debian|g' /etc/apt/sources.list) || true \
 && find /etc/apt/sources.list.d/ -type f -name '*.list' -exec sed -i 's|http://deb.debian.org/debian|http://ftp.us.debian.org/debian|g' {} + || true

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies with retry logic
RUN for i in 1 2 3; do apt-get update && apt-get install -y --fix-missing \
    # Basic utilities
    curl \
    wget \
    git \
    # Build dependencies
    build-essential \
    gcc \
    g++ \
    # PostgreSQL client libraries
    libpq-dev \
    # SSL certificates
    ca-certificates \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean && break || sleep 10; done

# Create app user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt requirements-dev.txt ./

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Development stage
FROM base as development

# Install development dependencies
RUN pip install -r requirements-dev.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium firefox webkit

# Copy source code
COPY . .

# Create directories and set permissions
RUN mkdir -p /app/data /app/logs /app/config && \
    chown -R appuser:appuser /app

# Switch to app user
USER appuser

# Expose ports
EXPOSE 8080

# Default command for development
CMD ["python", "-m", "scraper.main"]

# Production stage
FROM base as production

# Install only production dependencies
RUN pip install --no-deps -r requirements.txt

# Install Playwright browsers for production
RUN playwright install --with-deps chromium

# Copy source code
COPY --chown=appuser:appuser . .

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs /app/config && \
    chown -R appuser:appuser /app

# Switch to app user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose ports
EXPOSE 8080

# Production command
CMD ["python", "-m", "scraper.main"]
