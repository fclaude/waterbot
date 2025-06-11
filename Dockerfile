# WaterBot Dockerfile
# Multi-stage build for optimized production image

# Build stage
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Install the package
RUN pip install -e .

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN groupadd -r waterbot && useradd -r -g waterbot waterbot

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    # Signal CLI dependencies (Java)
    default-jre-headless \
    wget \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install Signal CLI
RUN wget -O /tmp/signal-cli.tar.gz \
    https://github.com/AsamK/signal-cli/releases/download/v0.11.12/signal-cli-0.11.12-Linux.tar.gz && \
    tar -xzf /tmp/signal-cli.tar.gz -C /opt/ && \
    ln -s /opt/signal-cli-*/bin/signal-cli /usr/local/bin/signal-cli && \
    rm /tmp/signal-cli.tar.gz

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
    CMD python -c "import waterbot.config; print('OK')" || exit 1

# Expose port for potential web interface
EXPOSE 8080

# Set default environment variables
ENV OPERATION_MODE=emulation
ENV LOG_LEVEL=INFO
ENV SCHEDULE_CONFIG_FILE=/app/data/schedules.json

# Default command
CMD ["python", "-m", "waterbot.bot"]

# Development stage (for local development)
FROM builder as development

# Install development dependencies
RUN pip install black flake8 isort mypy bandit safety pytest-watch

# Install pre-commit
RUN pip install pre-commit

# Set development environment variables
ENV OPERATION_MODE=emulation
ENV DEBUG_MODE=true
ENV LOG_LEVEL=DEBUG

# Default command for development
CMD ["python", "-m", "waterbot.bot"]
