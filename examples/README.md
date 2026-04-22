# HVACNetwork Examples

This directory contains example scripts demonstrating HVACNetwork capabilities.

## Quick Start Examples

### `simple_vav.py`
Basic VAV box simulation without networking. Great for understanding:
- VAV box creation and configuration
- Zone thermal modeling
- Mode transitions (heating/cooling/deadband)
- PID-controlled damper operation

```bash
uv run python examples/simple_vav.py
```

### `complete_building.py`
Full building simulation with multiple AHUs, chiller, and boiler. Demonstrates:
- Multi-zone coordination
- Plant equipment integration
- Supply air temperature reset
- Day-long simulation with varying conditions

```bash
uv run python examples/complete_building.py
```

## BACnet Examples

### `example_bacnet_simulation.py`
Basic BACnet/IP simulation with a single VAV box exposed as a BACnet device.

### `example_bacpypes3_simulation.py`
More comprehensive BACnet simulation using bacpypes3.

### `example_ahu_simulation.py`
AHU simulation with BACnet points.

### `example_building_simulation.py`
Building-level simulation with multiple equipment types.

## Equipment-Specific Examples

### `example_cooling_types.py`
Demonstrates different AHU cooling types:
- Chilled water cooling
- DX (direct expansion) cooling

### `example_thermal_simulation.py`
Detailed thermal modeling including:
- Solar gains by window orientation
- Thermal mass effects
- Occupancy schedules

### `example_complete_system.py`
Complete system with chiller plant, cooling tower, and boiler.

## Utility Examples

### `bacnet_device_config.py`
Helper for configuring BACnet device settings.

### `ip-to-vlan.py`
Network bridge between IP and virtual LAN for BACnet testing.

## Campus Examples

### `multi_building_campus.ttl`
Two-building campus example used by the default `./hvac-sim --campus` flow.

### `multi_building_campus_collisions.ttl`
Two-building campus example for multi-network testing. It uses explicit `bacnet:deviceId` annotations so one device in each building advertises the same BACnet device instance number on different networks.

### `large_campus.ttl`
Larger multi-building campus example for scale and layout testing.

### `test_campus.sh`
End-to-end helper for generating campus compose files, building images, starting the campus, and validating container health.

Examples:

```bash
# Default built-in campus scenario
./examples/test_campus.sh

# Explicit BACnet network numbers on the standard campus example
./examples/test_campus.sh --scenario multi-network

# Collision scenario using the checked-in example TTL
./examples/test_campus.sh --scenario multi-network-collisions
```

## Archived Examples

The `archive/` directory contains older examples that have been superseded:
- Large monolithic simulation files
- Brick-based simulation variants
- Earlier development iterations

These are kept for reference but are not recommended for new projects.

## Running Examples

Most examples can be run directly:

```bash
# Using uv (recommended)
uv run python examples/simple_vav.py

# Or with activated virtual environment
python examples/simple_vav.py
```

Some BACnet examples require network configuration. See the main project README for BACnet setup instructions.
