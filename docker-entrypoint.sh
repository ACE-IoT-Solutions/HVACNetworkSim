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

validate_ipv4_address() {
    python3 - "$1" <<'PY'
import ipaddress
import sys

try:
    print(ipaddress.IPv4Address(sys.argv[1]))
except ValueError:
    sys.exit(1)
PY
}

validate_bacnet_address() {
    python3 - "$1" <<'PY'
import ipaddress
import sys

try:
    interface = ipaddress.IPv4Interface(sys.argv[1])
except ValueError:
    sys.exit(1)

print(f"{interface.ip}/{interface.network.prefixlen}")
PY
}

validate_subnet_bits() {
    python3 - "$1" <<'PY'
import sys

try:
    bits = int(sys.argv[1])
except ValueError:
    sys.exit(1)

if bits < 0 or bits > 32:
    sys.exit(1)

print(bits)
PY
}

validate_port() {
    python3 - "$1" <<'PY'
import sys

try:
    port = int(sys.argv[1])
except ValueError:
    sys.exit(1)

if port < 1 or port > 65535:
    sys.exit(1)

print(port)
PY
}

validate_device_id() {
    python3 - "$1" <<'PY'
import sys

try:
    device_id = int(sys.argv[1])
except ValueError:
    sys.exit(1)

if device_id < 0 or device_id > 4194303:
    sys.exit(1)

print(device_id)
PY
}

validate_network_number() {
    python3 - "$1" <<'PY'
import sys

try:
    network_number = int(sys.argv[1])
except ValueError:
    sys.exit(1)

if network_number < 0 or network_number > 65534:
    sys.exit(1)

print(network_number)
PY
}

validate_network_number_list() {
    python3 - "$1" <<'PY'
import sys

parts = [part.strip() for part in sys.argv[1].split(",")]
if not parts or any(not part for part in parts):
    sys.exit(1)

validated = []
seen = set()
for part in parts:
    try:
        network_number = int(part)
    except ValueError:
        sys.exit(1)

    if network_number < 1 or network_number > 65534:
        sys.exit(1)
    if network_number in seen:
        continue
    seen.add(network_number)
    validated.append(str(network_number))

print(",".join(validated))
PY
}

exec_with_fault_control() {
    if [ -n "${FAULT_CONTROL_PORT:-}" ]; then
        if ! FAULT_CONTROL_PORT=$(validate_port "$FAULT_CONTROL_PORT"); then
            echo "Error: FAULT_CONTROL_PORT must be an integer between 1 and 65535"
            exit 1
        fi
        export FAULT_CONTROL_PORT
        echo "Fault Control Port: $FAULT_CONTROL_PORT"
    fi

    if [ -n "${FAULT_CONTROL_PORT:-}" ] || [ -n "${FAULT_CONTROL_STATE_FILE:-}" ]; then
        if [ -n "${FAULT_CONTROL_STATE_FILE:-}" ]; then
            echo "Fault Control State File: $FAULT_CONTROL_STATE_FILE"
        fi

        if [ -n "${FAULT_CONTROL_PORT:-}" ] && [ -n "${FAULT_CONTROL_STATE_FILE:-}" ]; then
            exec /app/.venv/bin/python -u /app/campus/fault_supervisor.py \
                --control-port "$FAULT_CONTROL_PORT" \
                --state-file "$FAULT_CONTROL_STATE_FILE" \
                -- "$@"
        fi

        if [ -n "${FAULT_CONTROL_PORT:-}" ]; then
            exec /app/.venv/bin/python -u /app/campus/fault_supervisor.py \
                --control-port "$FAULT_CONTROL_PORT" \
                -- "$@"
        fi

        exec /app/.venv/bin/python -u /app/campus/fault_supervisor.py \
            --state-file "$FAULT_CONTROL_STATE_FILE" \
            -- "$@"
    fi

    exec "$@"
}

# Normalize BACnet address configuration.
if [ -n "$BACNET_ADDRESS" ]; then
    if ! NORMALIZED_BACNET_ADDRESS=$(validate_bacnet_address "$BACNET_ADDRESS"); then
        echo "Error: BACNET_ADDRESS must be a valid IPv4 interface like 172.26.0.20/16"
        exit 1
    fi
    BACNET_IP="${NORMALIZED_BACNET_ADDRESS%/*}"
    BACNET_SUBNET="${NORMALIZED_BACNET_ADDRESS#*/}"
    echo "Using provided BACNET_ADDRESS: $NORMALIZED_BACNET_ADDRESS"
else
    if [ -z "$BACNET_IP" ]; then
        DETECTED_IP=$(auto_detect_ip)
        if [ -n "$DETECTED_IP" ]; then
            BACNET_IP="$DETECTED_IP"
            echo "Auto-detected container IP: $BACNET_IP"
        else
            echo "Warning: Could not auto-detect IP address. Using default 0.0.0.0"
            BACNET_IP="0.0.0.0"
        fi
    else
        echo "Using provided BACNET_IP: $BACNET_IP"
    fi

    if ! BACNET_IP=$(validate_ipv4_address "$BACNET_IP"); then
        echo "Error: BACNET_IP must be a valid IPv4 address"
        exit 1
    fi

    BACNET_SUBNET="${BACNET_SUBNET:-16}"
    if ! BACNET_SUBNET=$(validate_subnet_bits "$BACNET_SUBNET"); then
        echo "Error: BACNET_SUBNET must be an integer between 0 and 32"
        exit 1
    fi

    NORMALIZED_BACNET_ADDRESS="${BACNET_IP}/${BACNET_SUBNET}"
fi

export BACNET_IP BACNET_SUBNET
export BACNET_ADDRESS="$NORMALIZED_BACNET_ADDRESS"
echo "BACnet Address: $BACNET_ADDRESS"

# Set default port
BACNET_PORT="${BACNET_PORT:-47808}"
if ! BACNET_PORT=$(validate_port "$BACNET_PORT"); then
    echo "Error: BACNET_PORT must be an integer between 1 and 65535"
    exit 1
fi
export BACNET_PORT
echo "BACnet Port: $BACNET_PORT"

BACNET_DEVICE_ID="${BACNET_DEVICE_ID:-599}"
if ! BACNET_DEVICE_ID=$(validate_device_id "$BACNET_DEVICE_ID"); then
    echo "Error: BACNET_DEVICE_ID must be an integer between 0 and 4194303"
    exit 1
fi
export BACNET_DEVICE_ID

if [ -n "${BACNET_NETWORK_NUMBER:-}" ]; then
    if ! BACNET_NETWORK_NUMBER=$(validate_network_number "$BACNET_NETWORK_NUMBER"); then
        echo "Error: BACNET_NETWORK_NUMBER must be an integer between 0 and 65534"
        exit 1
    fi
    export BACNET_NETWORK_NUMBER
    echo "BACnet Network Number: $BACNET_NETWORK_NUMBER"
fi

if [ -n "${ROUTER_CLAIMED_NETWORKS:-}" ]; then
    if ! ROUTER_CLAIMED_NETWORKS=$(validate_network_number_list "$ROUTER_CLAIMED_NETWORKS"); then
        echo "Error: ROUTER_CLAIMED_NETWORKS must be a comma-separated list of integers between 1 and 65534"
        exit 1
    fi
    export ROUTER_CLAIMED_NETWORKS
    echo "Router Claimed Networks: $ROUTER_CLAIMED_NETWORKS"
fi

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
        echo "Using Brick TTL file: $(basename "$BRICK_TTL_FILE")"
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
objectIdentifier = ${BACNET_DEVICE_ID}
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
        exec_with_fault_control /app/.venv/bin/python -u /app/src/main.py
        ;;
    simple)
        echo "Starting simple VAV simulation..."
        exec_with_fault_control /app/.venv/bin/python -u /app/src/main.py
        ;;
    custom)
        # Allow running a custom script
        if [ "${ALLOW_CUSTOM_SCRIPT:-false}" != "true" ]; then
            echo "Error: custom mode requires ALLOW_CUSTOM_SCRIPT=true"
            exit 1
        fi
        if [ -n "$CUSTOM_SCRIPT" ] && [ -f "$CUSTOM_SCRIPT" ]; then
            echo "Running custom script: $CUSTOM_SCRIPT"
            exec_with_fault_control /app/.venv/bin/python -u "$CUSTOM_SCRIPT"
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
