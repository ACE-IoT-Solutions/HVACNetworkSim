# HVAC Network Simulation

A building HVAC simulation system that models realistic equipment behavior and exposes data via BACnet/IP. This enables testing of building automation systems, energy management software, and BACnet client applications without requiring physical equipment.

## Quick Start with Podman/Docker

The recommended way to run the simulation is using containers:

```bash
# Build the container image
podman build -t hvac-simulator .

# Run the simulation (BACnet on port 47808)
podman run --rm -p 47808:47808/udp hvac-simulator

# Run with custom settings
podman run --rm -p 47808:47808/udp \
  -e BACNET_DEVICE_ID=1000 \
  -e SIMULATION_MODE=simple \
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
| `CUSTOM_SCRIPT` | - | Path to custom Python script (for custom mode) |

### Running with Custom Brick Models

```bash
# Mount your Brick TTL files and run brick-based simulation
podman run --rm -p 47808:47808/udp \
  -v /path/to/your/models:/app/brick_schemas:ro \
  -e SIMULATION_MODE=brick \
  -e BRICK_TTL_FILE=/app/brick_schemas/building.ttl \
  hvac-simulator
```

### Running Custom Scripts

```bash
# Run a custom simulation script
podman run --rm -p 47808:47808/udp \
  -v /path/to/scripts:/app/custom:ro \
  -e SIMULATION_MODE=custom \
  -e CUSTOM_SCRIPT=/app/custom/my_simulation.py \
  hvac-simulator
```

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
│   └── points.py            # Point creation
├── vav_box.py              # VAV terminal unit
├── ahu.py                  # Air handling unit
├── chiller.py              # Chiller
├── boiler.py               # Boiler
├── cooling_tower.py        # Cooling tower
└── building.py             # Building container

examples/
├── simple_vav.py           # Basic VAV example
├── complete_building.py    # Full building simulation
└── ...                     # Additional examples

tests/
├── test_*.py               # Unit tests
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
  - Temperatures → Analog Input (AI)
  - Setpoints → Analog Value (AV)
  - Status → Binary Value (BV)
  - Modes → Multi-State Value (MSV)

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
- Automatic BACnet point generation
- Configuration via YAML or Python dataclasses
- Comprehensive test suite with performance benchmarks

## Requirements

- Python 3.12+
- Dependencies managed via `uv` (see `pyproject.toml`)
- Podman or Docker for containerized deployment

## License

See LICENSE file for details.
