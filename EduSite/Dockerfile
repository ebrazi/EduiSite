# Build stage
FROM python:3.10-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.10-slim

WORKDIR /app

# Create non-root user
RUN useradd --no-create-home --shell /bin/bash appuser

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Create instance directory for database and secrets
RUN mkdir -p instance && chown appuser:appuser instance

# Switch to non-root user
USER appuser

# Add user site-packages to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Environment variables (override in production)
ENV DEV_MODE=0
ENV SECRET_KEY=""
ENV ADMIN_PASSWORD=""
ENV MOCK_GATEWAY_SECRET=""
ENV DATABASE_PATH=/app/instance/edusite.db
ENV SITE_URL=http://localhost:5000

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/')" || exit 1

# Run with waitress (production WSGI server)
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "run:app"]