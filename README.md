# HVAC Network Simulation

A building HVAC simulation system that models realistic equipment behavior and exposes data via BACnet/IP. This enables testing of building automation systems, energy management software, and BACnet client applications without requiring physical equipment.

## Quick Start

The easiest way to run the simulation is with the `hvac-sim` CLI, which handles container setup automatically:

```bash
# Run simple VAV simulation
./hvac-sim

# Run with a Brick schema file
./hvac-sim bldg36.ttl

# List available Brick schema files
./hvac-sim --list
```

The CLI auto-detects Podman or Docker, builds the image if needed, and sets up all the correct volume mappings and environment variables.

Security defaults:
- Host networking requires `--allow-host-network`.
- Campus BBMD host ports and foreign-device registration require `--expose-campus-bacnet`.
- `-e/--env` only accepts `BACNET_ADDRESS`, `BACNET_IP`, `BACNET_SUBNET`, `BACNET_PORT`, and `BACNET_DEVICE_ID`.

### CLI Options

```bash
./hvac-sim [OPTIONS] [BRICK_FILE]

Options:
  -l, --list            List available Brick schema files
  -d, --detach          Run in background
  --device-id ID        BACnet device instance ID (default: 599)
  -p, --port PORT       Host port for BACnet UDP (default: 47808)
  --network MODE        Container network mode (e.g., 'host')
  --allow-host-network  Explicitly allow direct host-network exposure
  --build               Force rebuild the container image
  --stop                Stop the running simulation
  --logs                Show logs from the container
  -e KEY=VALUE          Set additional BACnet runtime variables
  --custom-script PATH  Run a mounted custom Python script
  --allow-custom-script Explicitly allow arbitrary custom script execution

Multi-building options:
  --multi-building      Enable multi-building mode with BBMD
  --inject-errors       Enable error injection for training/testing
  --duplicate-ids N     Inject N duplicate device IDs
  --duplicate-networks N  Inject N duplicate network numbers
  --duplicate-routers N   Inject N duplicate routers
  --expose-campus-bacnet  Publish campus BBMD ports and allow foreign devices
```

### Examples

```bash
# Run with a specific Brick file
./hvac-sim bldg36.ttl

# Run with custom device ID and port
./hvac-sim --device-id 1000 --port 47809 bldg36.ttl

# Run in background and view logs
./hvac-sim -d bldg36.ttl
./hvac-sim --logs

# Use host networking for BACnet discovery
./hvac-sim --network host --allow-host-network bldg36.ttl

# Stop the running simulation
./hvac-sim --stop

# Run multi-building campus simulation
./hvac-sim --multi-building examples/multi_building_campus.ttl

# Run a custom script with explicit acknowledgement
./hvac-sim --custom-script examples/example_simulation.py --allow-custom-script

# Run with error injection for training
./hvac-sim --inject-errors --duplicate-ids 2 bldg36.ttl
```

## Multi-Building Campus Simulation

The simulator supports multi-building campus simulations with BBMDs (BACnet Broadcast Management Devices) connecting buildings across a WAN:

```
Building 1 (Networks 1000-1999)       Building 2 (Networks 2000-2999)
        [BBMD-1] <---- WAN ----> [BBMD-2]
           |                        |
        [Router]                 [Router]
           |                        |
      [VLANs]                   [VLANs]
```

### Network Number Allocation

Each building gets a dedicated range of 1000 network numbers:

| Building | Network Range | Central Plant | AHU Networks |
|----------|---------------|---------------|--------------|
| Building 1 | 1000-1999 | 1001 | 1100, 1200, ... |
| Building 2 | 2000-2999 | 2001 | 2100, 2200, ... |
| Building N | N×1000-(N+1)×1000-1 | N×1000+1 | N×1000+100, ... |

### Sample Campus Files

| File | Buildings | AHUs | VAVs | Description |
|------|-----------|------|------|-------------|
| `multi_building_campus.ttl` | 2 | 2 | 7 | Small demo with 2 buildings |
| `large_campus.ttl` | 6 | 12 | 108 | Full campus simulation |

### Running Multi-Building Simulations

**Single-container mode** runs all buildings in one process (simulated BBMDs):

```bash
./hvac-sim --multi-building examples/multi_building_campus.ttl
```

**Multi-container campus mode** runs each building in its own container with real IP subnets and external [ace-acl-bbmd](https://github.com/ACE-IoT-Solutions/ace-acl-bbmd) instances for cross-building BACnet routing:

```bash
# Generate compose file, build images, and start the campus
# External BACnet exposure is disabled by default.
./hvac-sim --campus examples/multi_building_campus.ttl

# Publish BBMD ports and allow foreign-device registration explicitly
./hvac-sim --campus --expose-campus-bacnet examples/multi_building_campus.ttl

# View logs / stop
./hvac-sim --campus-logs
./hvac-sim --campus-stop
```

Campus mode requires the `ace-acl-bbmd` project as a sibling directory. The build patches its Dockerfile to use the `uv` base image and adds `--network=host` to work around Podman's default build isolation.

```bash
# With error injection for training
./hvac-sim --multi-building --inject-errors --duplicate-ids 5 examples/large_campus.ttl
```

### Large Campus Layout

The `large_campus.ttl` file simulates a university/corporate campus:

| Building | Description | Floors | AHUs | VAVs | Plant |
|----------|-------------|--------|------|------|-------|
| **Building A** | Administration | 3 | 2 | 16 | - |
| **Building B** | Engineering | 4 | 3 | 30 | - |
| **Building C** | Student Center | 2 | 2 | 20 | - |
| **Building D** | Library | 3 | 2 | 18 | - |
| **Building E** | Research Lab | 3 | 3 | 24 | - |
| **Central Plant** | Shared Infrastructure | - | - | - | 2 Chillers, 2 Boilers, 2 Cooling Towers |

### Creating Multi-Building TTL Files

Create a Brick schema with multiple `brick:Building` instances and use `brick:isPartOf` to associate equipment:

```turtle
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix ex: <http://example.com/building#> .

ex:Building1 a brick:Building .
ex:Building2 a brick:Building .

ex:AHU1 a brick:AHU ;
    brick:isPartOf ex:Building1 .

ex:AHU2 a brick:AHU ;
    brick:isPartOf ex:Building2 .
```

See `examples/multi_building_campus.ttl` for a basic example or `examples/large_campus.ttl` for a complete campus.

## Error Injection for Testing

The error injection feature deliberately creates BACnet configuration errors, useful for:
- Training BACnet troubleshooting tools
- Testing network diagnostic software
- Creating realistic error scenarios for education

### Error Types

| Error Type | Description |
|------------|-------------|
| Duplicate Device IDs | Multiple devices with the same BACnet device instance ID |
| Duplicate Network Numbers | Multiple networks claiming the same network number |
| Duplicate Routers | Multiple routers on the same network segment |

### Examples

```bash
# Inject 2 duplicate device IDs
./hvac-sim --inject-errors --duplicate-ids 2 bldg36.ttl

# Inject multiple error types
./hvac-sim --inject-errors --duplicate-ids 2 --duplicate-networks 1 bldg36.ttl

# Combine with multi-building mode
./hvac-sim --multi-building --inject-errors --duplicate-ids 3 examples/multi_building_campus.ttl
```

## Manual Container Commands

For more control, you can run the container directly:

```bash
# Build the container image
podman build -t hvac-simulator .

# Run simple simulation
podman run --rm -it -p 47808:47808/udp hvac-simulator

# Run with Brick schema
podman run --rm -it -p 47808:47808/udp \
  -v ./data/brick_schemas:/app/brick_schemas:ro \
  -e SIMULATION_MODE=brick \
  -e BRICK_TTL_FILE=/app/brick_schemas/bldg36.ttl \
  hvac-simulator
```

### Container Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACNET_IP` | auto-detected | BACnet device IP address |
| `BACNET_SUBNET` | 16 | Subnet mask bits (e.g., 16 = /16) |
| `BACNET_PORT` | 47808 | BACnet UDP port |
| `BACNET_DEVICE_ID` | 599 | BACnet device instance ID |
| `SIMULATION_MODE` | simple | Simulation mode: `simple`, `brick`, or `custom` |
| `BRICK_TTL_FILE` | - | Path to Brick TTL file (for brick mode) |
| `CUSTOM_SCRIPT` | - | Path to custom Python script (for custom mode; use `--custom-script`) |
| `ALLOW_CUSTOM_SCRIPT` | false | Required to run `CUSTOM_SCRIPT` in custom mode |
| `MULTI_BUILDING_MODE` | false | Enable multi-building campus simulation |
| `INJECT_ERRORS` | false | Enable error injection mode |
| `DUPLICATE_DEVICE_IDS` | 0 | Number of duplicate device IDs to inject |
| `DUPLICATE_NETWORK_NUMBERS` | 0 | Number of duplicate network numbers to inject |
| `DUPLICATE_ROUTERS` | 0 | Number of duplicate routers to inject |

## Local Development

For development, you can run directly with `uv`:

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run a simple example
uv run python examples/simple_vav.py

# Run the full building example
uv run python examples/complete_building.py

# Run the main BACnet simulation
uv run python src/main.py
```

## Components

### Terminal Equipment

- **VAV Box**: Variable Air Volume terminal unit with optional reheat capability
  - Modulates airflow in cooling mode
  - Controls reheat valve in heating mode
  - Maintains minimum airflow in deadband mode
  - Models thermal behavior with occupancy and solar heat gain

### Air-Side Equipment

- **Air Handling Unit (AHU)**: Central unit supplying conditioned air to VAV boxes
  - Controls supply air temperature
  - Coordinates multiple VAV boxes
  - Optional supply air temperature reset
  - Supports chilled water and DX cooling

### Plant Equipment

- **Chiller**: Produces chilled water for cooling coils
  - Water-cooled and air-cooled configurations
  - COP modeling based on load and conditions
  - Integrates with cooling tower

- **Cooling Tower**: Evaporative heat rejection for water-cooled chillers
  - Variable-speed fan control
  - Approach temperature modeling
  - Multi-cell support

- **Boiler**: Produces hot water for heating coils
  - Gas-fired and electric configurations
  - Condensing boiler efficiency modeling
  - Realistic cycling behavior

### Building Container

- **Building**: Top-level container for HVAC equipment
  - Manages multiple AHUs and zones
  - Tracks weather conditions
  - Calculates solar position
  - Energy reporting

## Project Structure

```
src/
├── core/                    # Core infrastructure
│   ├── constants.py         # Physics constants
│   ├── config.py            # Configuration system
│   └── logging.py           # Structured logging
├── physics/                 # Physics calculations
│   ├── thermal.py           # Heat transfer
│   └── fluid.py             # Fluid dynamics
├── controls/                # Control systems
│   └── pid.py               # PID controller
├── equipment/               # Equipment base classes
│   └── base.py              # Abstract hierarchy
├── bacnet/                  # BACnet integration
│   ├── device.py            # Device management
│   ├── mixin.py             # Application mixin
│   ├── points.py            # Point creation & unit mapping
│   ├── router_metrics.py    # Router diagnostic instrumentation
│   ├── bbmd.py              # BBMD management
│   └── errors.py            # Error injection
├── brick/                   # Brick schema parsing
│   ├── parser.py            # TTL file parser
│   └── campus.py            # Multi-building structures
├── vav_box.py              # VAV terminal unit
├── ahu.py                  # Air handling unit
├── chiller.py              # Chiller
├── boiler.py               # Boiler
├── cooling_tower.py        # Cooling tower
├── building.py             # Building container
└── bacnet_network.py       # Network management

examples/
├── simple_vav.py           # Basic VAV example
├── complete_building.py    # Full building simulation
├── multi_building_campus.ttl  # 2-building demo (7 VAVs)
├── large_campus.ttl        # Full campus (6 buildings, 108 VAVs)
└── ...                     # Additional examples

tests/
├── test_*.py               # Unit tests
├── test_multi_building.py  # Multi-building tests
├── test_bbmd_errors.py     # BBMD and error tests
├── integration/            # Integration tests
└── performance/            # Performance benchmarks
```

## Configuration

Equipment can be configured via YAML files or dataclasses:

```yaml
# config.yaml
simulation:
  time_step_minutes: 1
  speed_multiplier: 60

bacnet:
  port: 47808
  device_id_base: 1000

defaults:
  vav:
    min_airflow: 100
    max_airflow: 1000
    zone_temp_setpoint: 72
```

```python
from src.core.config import VAVConfig, ThermalZoneConfig
from src.vav_box import VAVBox

config = VAVConfig(
    name="VAV-101",
    min_airflow=100,
    max_airflow=800,
    thermal_zone=ThermalZoneConfig(
        zone_area=400,
        window_orientation="east"
    )
)
vav = VAVBox.from_config(config)
```

## BACnet Integration

The simulation exposes all equipment as BACnet devices:

- Each equipment instance gets a unique BACnet device ID
- Process variables are mapped to BACnet objects:
  - Temperatures → Analog Value (AV) with degrees-fahrenheit
  - Setpoints → Analog Value (AV) with degrees-fahrenheit
  - Airflows → Analog Value (AV) with cubic-feet-per-minute
  - Valve/damper positions → Analog Value (AV) with percent
  - Status → Binary Value (BV)
  - Modes → Multi-State Value (MSV) with stateText
- All numeric points carry proper BACnet engineering units (no-units for dimensionless values like COP and ratios)

### Change of Value (COV) Notifications

All simulated BACnet objects support COV subscriptions:

- **Analog values** use `COVIncrementCriteria` — notifications fire only when the change exceeds `covIncrement` (default 0.1), filtering out noise from minor simulation fluctuations
- **Binary values** use `GenericCriteria` — notifications fire on any state change
- **Multi-state values** use `GenericCriteria` — notifications fire on any state transition

Clients subscribe via the standard BACnet `SubscribeCOV` service. The initial notification on subscribe delivers the current value, and subsequent notifications arrive as the simulation updates equipment state (once per simulation tick).

### Router Diagnostics

Each building's IP-to-VLAN router device exposes operational metrics as BACnet analog values:

| Point | Object ID | Description |
|-------|-----------|-------------|
| `packets_routed` | analog-value,100 | Total NPDUs routed between networks |
| `packets_from_ip` | analog-value,101 | NPDUs received from BACnet/IP |
| `packets_to_ip` | analog-value,102 | NPDUs sent to BACnet/IP |
| `who_is_requests` | analog-value,103 | Who-Is requests processed |
| `i_am_responses` | analog-value,104 | I-Am responses sent |
| `read_property_requests` | analog-value,105 | ReadProperty requests handled |
| `write_property_requests` | analog-value,106 | WriteProperty requests handled |
| `cov_notifications` | analog-value,107 | COV notifications forwarded |
| `rejected_packets` | analog-value,108 | Dropped/rejected packets |
| `uptime_seconds` | analog-value,109 | Router uptime in seconds |
| `connected_networks` | analog-value,110 | Number of connected VLANs |

These counters are COV-subscribable (covIncrement=1.0) and update each simulation tick.

### Discovering Simulated Devices

Use any BACnet client to discover the simulated equipment:
- BAC0 Python library
- YABE (Yet Another BACnet Explorer)
- Proprietary BMS systems with BACnet/IP

## Testing

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test category
uv run pytest tests/integration/
uv run pytest tests/performance/

# Run with coverage
uv run pytest --cov=src
```

## Documentation

- [Architecture Guide](docs/architecture.md) - System design and physics models
- [Examples README](examples/README.md) - Example script documentation

## Features

- Realistic PID control for damper and valve modulation
- Dynamic thermal modeling with solar gains and occupancy
- Multiple cooling system types (chilled water, DX)
- Central plant equipment with performance curves
- Standardized process variable interface
- Automatic BACnet point generation with proper engineering units
- COV (Change of Value) notifications on all simulated points
- Router diagnostic counters (packets routed, request counts, uptime)
- Configuration via YAML or Python dataclasses
- Comprehensive test suite with performance benchmarks
- Multi-building campus simulation with BBMD routing
- Multi-container campus mode with real IP subnets and ace-acl-bbmd
- Error injection for training and testing BACnet tools
- Brick schema support for equipment topology

## Requirements

- Python 3.12+
- Dependencies managed via `uv` (see `pyproject.toml`)
- Podman or Docker for containerized deployment

## License

See LICENSE file for details.
