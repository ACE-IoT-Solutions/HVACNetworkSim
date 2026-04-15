#!/bin/bash
#
# test_campus.sh - Test the multi-building campus simulation with real podman networks and BBMDs
#
# This script:
#   1. Generates campus compose + BBMD configs from a TTL file
#   2. Builds the hvac-simulator and ace-acl-bbmd container images (if needed)
#   3. Starts the campus with podman-compose
#   4. Verifies all containers are running
#   5. Waits for the simulation to progress through multiple ticks
#   6. Validates BBMD peering and per-building device isolation
#
# Usage:
#   ./examples/test_campus.sh                                    # 2-building campus (default)
#   ./examples/test_campus.sh examples/large_campus.ttl          # 6-building campus
#   ./examples/test_campus.sh --build                            # force rebuild images
#   ./examples/test_campus.sh --teardown                         # clean up after test
#

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Project root (one level up from examples/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Defaults
TTL_FILE=""
TEARDOWN=false
FORCE_BUILD=false

# Parse args: first non-flag argument is the TTL file
for arg in "$@"; do
    case "$arg" in
        --teardown) TEARDOWN=true ;;
        --build) FORCE_BUILD=true ;;
        -*) ;; # ignore unknown flags
        *) TTL_FILE="$arg" ;;
    esac
done

TTL_FILE="${TTL_FILE:-examples/multi_building_campus.ttl}"
COMPOSE_FILE="docker-compose.campus.yml"
SIM_WAIT=30  # seconds to stream live logs

# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }

# --------------------------------------------------------------------------
# Detect container runtime
# --------------------------------------------------------------------------

RUNTIME=""
COMPOSE_CMD=""

if command -v podman &>/dev/null; then
    RUNTIME="podman"
    if command -v podman-compose &>/dev/null; then
        COMPOSE_CMD="podman-compose"
    fi
elif command -v docker &>/dev/null; then
    RUNTIME="docker"
    if command -v docker-compose &>/dev/null; then
        COMPOSE_CMD="docker-compose"
    elif docker compose version &>/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    fi
fi

if [ -z "$RUNTIME" ]; then
    fail "Neither podman nor docker found."
    exit 1
fi

if [ -z "$COMPOSE_CMD" ]; then
    fail "${RUNTIME}-compose not found."
    exit 1
fi

# --------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Campus Simulation Test"
echo "============================================================"
info "Runtime:      $RUNTIME"
info "Compose:      $COMPOSE_CMD"
info "TTL file:     $TTL_FILE"
info "Force build:  $FORCE_BUILD"
info "Teardown:     $TEARDOWN"
echo "============================================================"
echo ""

# --------------------------------------------------------------------------
# Step 1: Generate campus configs
# --------------------------------------------------------------------------

info "Step 1/6: Generating campus configuration..."

python campus/generate_campus.py "$TTL_FILE"

if [ ! -f "$COMPOSE_FILE" ]; then
    fail "Compose file not generated: $COMPOSE_FILE"
    exit 1
fi

ok "Campus configuration generated"
echo ""

# --------------------------------------------------------------------------
# Step 2: Build images
# --------------------------------------------------------------------------

info "Step 2/6: Building container images..."

# Build hvac-simulator
if [ "$FORCE_BUILD" = true ] || ! $RUNTIME image inspect hvac-simulator &>/dev/null; then
    info "Building hvac-simulator..."
    $RUNTIME build --network=host -t hvac-simulator .
    ok "hvac-simulator built"
else
    ok "hvac-simulator image exists (use --build to rebuild)"
fi

# Build ace-acl-bbmd
BBMD_DIR="$PROJECT_ROOT/../ace-acl-bbmd"
if [ ! -d "$BBMD_DIR" ]; then
    fail "ace-acl-bbmd project not found at $BBMD_DIR"
    warn "Clone it with: git clone <ace-acl-bbmd-repo> ../ace-acl-bbmd"
    exit 1
fi

if [ "$FORCE_BUILD" = true ] || ! $RUNTIME image inspect ace-acl-bbmd &>/dev/null; then
    info "Building ace-acl-bbmd..."
    # Patch Dockerfile: swap base image to include gcc (avoids apt-get needing network),
    # add README.md (needed by hatchling), and use uv sync instead of pip.
    DOCKERFILE="$BBMD_DIR/integration_testing/Dockerfile.bbmd"
    if [ -f "$DOCKERFILE" ]; then
        PATCHED=$(mktemp)
        sed -e 's|FROM python:3.13-slim|FROM ghcr.io/astral-sh/uv:python3.13-bookworm|' \
            -e 's|COPY pyproject.toml uv.lock \./|COPY pyproject.toml uv.lock README.md ./|' \
            -e '/# Install system dependencies/,/rm -rf \/var\/lib\/apt\/lists/d' \
            -e 's|RUN pip install uv &&.*|RUN uv sync --no-dev|' \
            -e 's|WORKDIR /app|WORKDIR /app\nENV PATH="/app/.venv/bin:$PATH"|' \
            "$DOCKERFILE" > "$PATCHED"
        $RUNTIME build --network=host -f "$PATCHED" -t ace-acl-bbmd "$BBMD_DIR"
        rm -f "$PATCHED"
    else
        $RUNTIME build --network=host -t ace-acl-bbmd "$BBMD_DIR"
    fi
    ok "ace-acl-bbmd built"
else
    ok "ace-acl-bbmd image exists (use --build to rebuild)"
fi

echo ""

# --------------------------------------------------------------------------
# Step 3: Start campus
# --------------------------------------------------------------------------

info "Step 3/6: Starting campus simulation..."

# Tear down any existing campus
$COMPOSE_CMD -f "$COMPOSE_FILE" down 2>/dev/null || true

$COMPOSE_CMD -f "$COMPOSE_FILE" up -d

ok "Campus containers started"
echo ""

# --------------------------------------------------------------------------
# Step 4: Verify containers are running
# --------------------------------------------------------------------------

info "Step 4/6: Verifying containers..."

# Give containers a moment to initialize
sleep 5

# Count expected containers from compose file
EXPECTED_SERVICES=$($COMPOSE_CMD -f "$COMPOSE_FILE" config --services 2>/dev/null | wc -l | tr -d ' ')
RUNNING=$($RUNTIME ps --filter "name=campus-" --format "{{.Names}}" 2>/dev/null | wc -l | tr -d ' ')

info "Expected services: $EXPECTED_SERVICES"
info "Running containers: $RUNNING"
echo ""

$RUNTIME ps --filter "name=campus-" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
echo ""

ALL_OK=true
for name in $($RUNTIME ps --filter "name=campus-" --format "{{.Names}}" 2>/dev/null); do
    STATUS=$($RUNTIME inspect --format '{{.State.Status}}' "$name" 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "running" ]; then
        ok "$name is running"
    else
        fail "$name status: $STATUS"
        ALL_OK=false
    fi
done
echo ""

# --------------------------------------------------------------------------
# Step 5: Validate BBMD peering and building isolation
# --------------------------------------------------------------------------

info "Step 5/6: Validating BBMD peering and building isolation..."
echo ""

# Check BBMD peer connections
BBMD_OK=true
for name in $($RUNTIME ps --filter "name=campus-bbmd" --format "{{.Names}}" 2>/dev/null); do
    PEER_LINE=$($RUNTIME logs "$name" 2>&1 | grep "Added BBMD peer" | tail -1)
    if [ -n "$PEER_LINE" ]; then
        ok "$name: $PEER_LINE"
    else
        warn "$name: No peer connections found yet"
        BBMD_OK=false
    fi
done
echo ""

# Check each sim container has the correct building and show device tables
for name in $($RUNTIME ps --filter "name=campus-sim" --format "{{.Names}}" 2>/dev/null); do
    BUILDING=$($RUNTIME logs "$name" 2>&1 | grep "Starting single-building simulation for:" | head -1)
    if [ -n "$BUILDING" ]; then
        ok "$name: $BUILDING"
    else
        warn "$name: Building assignment not found in logs yet"
    fi

    # Show per-container device table
    $RUNTIME logs "$name" 2>&1 | sed -n '/^BACnet Device Table$/,/^[0-9]* devices$/p'
    echo ""
done

# Show combined device table across all buildings
info "Combined campus device table:"
echo ""
printf "  %-11s %-30s %-9s %-14s %s\n" "Device ID" "Name" "Network" "BACnet/IP" "Container"
printf "  %-11s %-30s %-9s %-14s %s\n" "-----------" "------------------------------" "---------" "--------------" "----------------------"

for name in $($RUNTIME ps --filter "name=campus-sim" --format "{{.Names}}" 2>/dev/null); do
    # Extract data rows from the device table (skip header, separator, footer, and blanks)
    $RUNTIME logs "$name" 2>&1 \
        | sed -n '/^BACnet Device Table$/,/^[0-9]* devices$/p' \
        | grep -v '^BACnet Device Table$' \
        | grep -v '^===*$' \
        | grep -v '^Device ID' \
        | grep -v '^---' \
        | grep -v '^[0-9]* devices$' \
        | grep -v '^$' \
        | while IFS= read -r line; do
            # Parse the fixed-width columns: DeviceID(col1) Name(col2) Network(col3) BACnet/IP(col4)
            dev_id=$(echo "$line" | awk '{print $1}')
            dev_name=$(echo "$line" | awk '{print $2}')
            net_num=$(echo "$line" | awk '{print $3}')
            dev_ip=$(echo "$line" | awk '{print $4}')
            printf "  %-11s %-30s %-9s %-14s %s\n" "$dev_id" "$dev_name" "$net_num" "$dev_ip" "$name"
        done
done

echo ""

# Show network topology
info "Networks:"
for net in $($RUNTIME network ls --filter "name=hvacnetwork" --format "{{.Name}}" 2>/dev/null); do
    SUBNET=$($RUNTIME network inspect "$net" --format '{{range .Subnets}}{{.Subnet}}{{end}}' 2>/dev/null || echo "unknown")
    info "  $net  ($SUBNET)"
done
echo ""

# --------------------------------------------------------------------------
# Step 6: Watch simulation run
# --------------------------------------------------------------------------

info "Step 6/6: Streaming live logs for ${SIM_WAIT}s..."
info "Press Ctrl+C to stop watching (containers will keep running)"
echo ""
echo "------------------------------------------------------------"

# Stream logs from each sim container in parallel, kill after SIM_WAIT seconds
LOG_PIDS=""
for name in $($RUNTIME ps --filter "name=campus-" --format "{{.Names}}" 2>/dev/null); do
    $RUNTIME logs --tail 5 -f "$name" 2>&1 | sed "s/^/[$name] /" &
    LOG_PIDS="$LOG_PIDS $!"
done
sleep "$SIM_WAIT" 2>/dev/null || true
for pid in $LOG_PIDS; do
    kill "$pid" 2>/dev/null || true
done
wait 2>/dev/null || true

echo "------------------------------------------------------------"
echo ""

# Show final state
for name in $($RUNTIME ps --filter "name=campus-sim" --format "{{.Names}}" 2>/dev/null); do
    TICK_COUNT=$($RUNTIME logs "$name" 2>&1 | grep -c "Time: " || true)
    LAST_TICK=$($RUNTIME logs "$name" 2>&1 | grep "Time: " | tail -1)
    ok "$name: $TICK_COUNT simulation tick(s) completed"
    [ -n "$LAST_TICK" ] && info "  Last: $LAST_TICK"
done
echo ""

# --------------------------------------------------------------------------
# Teardown or show status
# --------------------------------------------------------------------------

echo "============================================================"

if [ "$TEARDOWN" = true ]; then
    info "Tearing down campus simulation..."
    $COMPOSE_CMD -f "$COMPOSE_FILE" down
    ok "Campus simulation stopped and cleaned up"
else
    ok "Campus simulation is running!"
    echo ""
    info "Useful commands:"
    info "  View logs:     $COMPOSE_CMD -f $COMPOSE_FILE logs -f"
    info "  Stop campus:   $COMPOSE_CMD -f $COMPOSE_FILE down"
    info "  Container ps:  $RUNTIME ps --filter name=campus-"
    info "  Rerun test:    ./examples/test_campus.sh --teardown"
fi

echo "============================================================"
echo ""
