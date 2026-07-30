# WaterBot Dockerfile
# Multi-stage build for optimized production image

# Build stage
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt requirements-dev.txt ./

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Install the package
RUN pip install --no-cache-dir -e .

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN groupadd -r waterbot && useradd -r -g waterbot waterbot

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Copy application code
COPY --from=builder /app /app

# Create directories for logs and schedules
RUN mkdir -p /app/logs /app/data && \
    chown -R waterbot:waterbot /app

# Switch to non-root user
USER waterbot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')" || \
        python -c "import waterbot; print('OK')"

# Expose port for the optional web interface
EXPOSE 8080

# Set default environment variables
ENV OPERATION_MODE=emulation
ENV LOG_LEVEL=INFO
ENV SCHEDULE_CONFIG_FILE=/app/data/schedules.json
ENV POLICY_SCHEDULE_CONFIG_FILE=/app/data/schedule_policies.json
ENV AGENT_DB_FILE=/app/data/waterbot_agent.db
ENV WEB_HOST=127.0.0.1

# Default command
CMD ["python", "-m", "waterbot.bot"]

# Development stage (for local development)
FROM builder as development

# Install development dependencies
RUN pip install --no-cache-dir -r requirements-dev.txt

# Set development environment variables
ENV OPERATION_MODE=emulation
ENV DEBUG_MODE=true
ENV LOG_LEVEL=DEBUG

# Default command for development
CMD ["python", "-m", "waterbot.bot"]
