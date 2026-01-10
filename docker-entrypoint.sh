#!/bin/sh
set -e

# Auto-detect container IP address if not provided
# This finds the primary non-loopback IPv4 address
auto_detect_ip() {
    # Try to get IP from hostname -I (most reliable in containers)
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')

    # If that fails, try ip command
    if [ -z "$IP" ]; then
        IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1 2>/dev/null)
    fi

    # If that fails, try ifconfig
    if [ -z "$IP" ]; then
        IP=$(ifconfig 2>/dev/null | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
    fi

    echo "$IP"
}

# Get the container IP
if [ -z "$BACNET_IP" ]; then
    DETECTED_IP=$(auto_detect_ip)
    if [ -n "$DETECTED_IP" ]; then
        export BACNET_IP="$DETECTED_IP"
        echo "Auto-detected container IP: $BACNET_IP"
    else
        echo "Warning: Could not auto-detect IP address. Using default 0.0.0.0"
        export BACNET_IP="0.0.0.0"
    fi
else
    echo "Using provided BACNET_IP: $BACNET_IP"
fi

# Set default subnet mask if not provided (default /16 for Docker networks)
BACNET_SUBNET="${BACNET_SUBNET:-16}"
export BACNET_ADDRESS="${BACNET_IP}/${BACNET_SUBNET}"
echo "BACnet Address: $BACNET_ADDRESS"

# Set default port
BACNET_PORT="${BACNET_PORT:-47808}"
export BACNET_PORT
echo "BACnet Port: $BACNET_PORT"

# Handle TTL file for brick-based simulation
if [ -n "$BRICK_TTL_FILE" ]; then
    if [ -f "$BRICK_TTL_FILE" ]; then
        echo "Using Brick TTL file: $BRICK_TTL_FILE"
        export BRICK_TTL_FILE
    else
        echo "Error: Brick TTL file not found: $BRICK_TTL_FILE"
        echo "Make sure to mount the file or volume containing your TTL files."
        exit 1
    fi
fi

# Create configs directory if needed
mkdir -p /app/configs

# Create BACnet device configuration
cat > /app/configs/bacnet_config.ini <<EOF
[BACpypes]
objectName = HVACSimulator
address = ${BACNET_ADDRESS}:${BACNET_PORT}
objectIdentifier = ${BACNET_DEVICE_ID:-599}
maxApduLengthAccepted = 1024
segmentationSupported = segmentedBoth
vendorIdentifier = 15
EOF

echo "Created BACnet configuration at /app/configs/bacnet_config.ini"

# Determine which simulation mode to run
SIMULATION_MODE="${SIMULATION_MODE:-simple}"
echo "Simulation mode: $SIMULATION_MODE"

case "$SIMULATION_MODE" in
    brick)
        if [ -z "$BRICK_TTL_FILE" ]; then
            echo "Error: BRICK_TTL_FILE must be set for brick simulation mode"
            exit 1
        fi
        echo "Starting Brick-based simulation with $BRICK_TTL_FILE..."
        exec uv run python -u /app/src/main.py
        ;;
    simple)
        echo "Starting simple VAV simulation..."
        exec uv run python -u /app/src/main.py
        ;;
    custom)
        # Allow running a custom script
        if [ -n "$CUSTOM_SCRIPT" ] && [ -f "$CUSTOM_SCRIPT" ]; then
            echo "Running custom script: $CUSTOM_SCRIPT"
            exec uv run python -u "$CUSTOM_SCRIPT"
        else
            echo "Error: CUSTOM_SCRIPT not set or file not found"
            exit 1
        fi
        ;;
    *)
        echo "Unknown simulation mode: $SIMULATION_MODE"
        echo "Valid modes: simple, brick, custom"
        exit 1
        ;;
esac
