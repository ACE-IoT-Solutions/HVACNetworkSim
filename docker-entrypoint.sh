#!/bin/sh
set -e

# Auto-detect container IP address if not provided
# This finds the primary non-loopback IPv4 address
auto_detect_ip() {
    # Try to get IP from hostname -I (most reliable in containers)
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')

    # If that fails, try reading from /proc (no iproute2 needed)
    if [ -z "$IP" ]; then
        IP=$(python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('10.255.255.255',1)); print(s.getsockname()[0]); s.close()" 2>/dev/null)
    fi

    # If that fails, try /proc/net/fib_trie (Linux-only, no external tools)
    if [ -z "$IP" ]; then
        IP=$(awk '/32 host/ { print f } {f=$2}' /proc/net/fib_trie 2>/dev/null | grep -v '127.0.0.1' | head -1)
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

# Handle BUILDING_NAME for campus multi-container mode
if [ -n "$BUILDING_NAME" ]; then
    echo "Building Name: $BUILDING_NAME (campus multi-container mode)"
    export BUILDING_NAME
fi

# Set up cross-subnet routes for campus mode
# CAMPUS_ROUTES format: "10.2.0.0/24:10.1.0.254,10.3.0.0/24:10.1.0.254"
if [ -n "$CAMPUS_ROUTES" ]; then
    echo "Setting up campus cross-subnet routes..."
    for route in $(echo "$CAMPUS_ROUTES" | tr ',' ' '); do
        subnet=$(echo "$route" | cut -d: -f1)
        gateway=$(echo "$route" | cut -d: -f2)
        # Convert CIDR to dest + netmask for add_route.py
        dest=$(echo "$subnet" | cut -d/ -f1)
        cidr=$(echo "$subnet" | cut -d/ -f2)
        netmask=$(python3 -c "import ipaddress; print(ipaddress.IPv4Network('0.0.0.0/${cidr}').netmask)")
        echo "  Adding route: $subnet via $gateway"
        python3 /app/campus/add_route.py "$dest" "$netmask" "$gateway" 2>/dev/null || echo "  Warning: Failed to add route $subnet via $gateway"
    done
fi

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
        exec /app/.venv/bin/python -u /app/src/main.py
        ;;
    simple)
        echo "Starting simple VAV simulation..."
        exec /app/.venv/bin/python -u /app/src/main.py
        ;;
    custom)
        # Allow running a custom script
        if [ -n "$CUSTOM_SCRIPT" ] && [ -f "$CUSTOM_SCRIPT" ]; then
            echo "Running custom script: $CUSTOM_SCRIPT"
            exec /app/.venv/bin/python -u "$CUSTOM_SCRIPT"
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
