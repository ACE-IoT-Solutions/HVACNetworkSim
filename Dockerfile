#FROM python:3.12-slim
FROM ghcr.io/astral-sh/uv:python3.12-trixie

# Install system dependencies including iproute2 for IP detection
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    curl \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY examples/ ./examples/
COPY data/ ./data/

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create directories for config and TTL files
RUN mkdir -p /app/configs /app/brick_schemas

# Install Python dependencies
RUN uv sync

# Expose BACnet port
EXPOSE 47808/udp

# Set environment variables
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONUNBUFFERED=1

# Default environment variables (can be overridden at runtime)
# BACNET_IP will be auto-detected if not set
ENV BACNET_SUBNET=16
ENV BACNET_PORT=47808
ENV SIMULATION_MODE=simple

# Volume mount points for external TTL files
# Mount your Brick TTL files to /app/brick_schemas
VOLUME ["/app/brick_schemas", "/app/configs"]

# Use entrypoint script for flexible startup
ENTRYPOINT ["/docker-entrypoint.sh"]
