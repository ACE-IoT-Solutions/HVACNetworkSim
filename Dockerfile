#FROM python:3.12-slim
FROM ghcr.io/astral-sh/uv:python3.12-trixie

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY examples/ ./examples/
COPY data/ ./data/

# Install Python dependencies
RUN uv sync

# Expose BACnet port
EXPOSE 47808/udp

# Set environment variables
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONUNBUFFERED=1

# Run the working BACnet simulation
CMD ["python", "-u", "examples/example_bacnet_simulation.py"]
