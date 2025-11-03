FROM python:3.12-slim

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
COPY pyproject.toml README.md uv.lock* ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel
RUN pip install uv
RUN uv pip install --system -e .

# Create config directory
RUN mkdir -p /app/configs

# Copy startup script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose BACnet port
EXPOSE 47808/udp

# Set environment variables
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "src/main.py"]