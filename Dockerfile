FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /hvac

# Copy source code
COPY . /hvac/

# Install Python dependencies
RUN pip install --no-cache-dir bacpypes3

# Expose BACnet/IP port (UDP 47808)
EXPOSE 47808/udp

# Run the BACnet simulation with unbuffered output
CMD ["python", "-u", "example_bacnet_simulation.py"]
