#FROM python:3.12-slim
FROM ghcr.io/astral-sh/uv:python3.12-trixie

# Note: gcc, g++, make, curl are already in the uv base image.
# Route management uses campus/add_route.py (ioctl) instead of iproute2.

# Set working directory
WORKDIR /app

# Copy project files (uv.lock ensures reproducible dependency resolution)
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY campus/add_route.py ./campus/add_route.py
COPY examples/ ./examples/
COPY data/ ./data/

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create directories for config and TTL files
RUN mkdir -p /app/configs /app/brick_schemas

# Install Python dependencies
RUN uv sync --no-dev

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
