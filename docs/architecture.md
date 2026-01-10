# HVACNetwork Architecture

This document describes the architecture of the HVACNetwork BACnet simulation system.

## Overview

HVACNetwork is a building HVAC simulation system that models realistic equipment behavior and exposes data via BACnet/IP. It enables testing of building automation systems, energy management software, and BACnet client applications without requiring physical equipment.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HVACNetwork System                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │
│  │   VAVBox    │   │     AHU     │   │  Building   │                │
│  │  (Terminal) │◄──│ (Air Side)  │◄──│ (Container) │                │
│  └─────────────┘   └─────────────┘   └─────────────┘                │
│         │                │                  │                        │
│         │                │                  │                        │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │
│  │   Boiler    │   │   Chiller   │◄──│CoolingTower │                │
│  │  (Heating)  │   │  (Cooling)  │   │  (Reject)   │                │
│  └─────────────┘   └─────────────┘   └─────────────┘                │
│         │                │                  │                        │
│         └────────────────┴──────────────────┘                        │
│                          │                                           │
│                    ┌─────┴─────┐                                    │
│                    │  BACnet   │                                    │
│                    │  Network  │                                    │
│                    └───────────┘                                    │
│                          │                                           │
└──────────────────────────┼──────────────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │ BACnet/IP   │
                    │  Clients    │
                    └─────────────┘
```

## Module Structure

```
src/
├── core/                    # Core infrastructure
│   ├── constants.py         # Physics and engineering constants
│   ├── config.py            # Configuration dataclasses
│   ├── logging.py           # Structured logging setup
│   └── exceptions.py        # Custom exceptions
│
├── physics/                 # Physics calculations
│   ├── thermal.py           # Heat transfer calculations
│   └── fluid.py             # Fluid dynamics calculations
│
├── controls/                # Control systems
│   └── pid.py               # PID controller implementation
│
├── equipment/               # Equipment base classes
│   └── base.py              # Abstract equipment hierarchy
│
├── bacnet/                  # BACnet integration
│   ├── device.py            # BACnet device management
│   ├── mixin.py             # BACnet application mixin
│   └── points.py            # BACnet point creation helpers
│
├── vav_box.py              # VAV box terminal unit
├── ahu.py                  # Air handling unit
├── chiller.py              # Chiller plant equipment
├── boiler.py               # Boiler plant equipment
├── cooling_tower.py        # Cooling tower
├── building.py             # Building container
├── bacnet_network.py       # BACnet network topology
└── main.py                 # Application entry point
```

## Class Hierarchy

### Equipment Classes

```
Equipment (ABC)
├── TerminalUnit (ABC)
│   └── VAVBox
├── AirHandler (ABC)
│   └── AirHandlingUnit
├── PlantEquipment (ABC)
│   ├── Chiller
│   ├── Boiler
│   └── CoolingTower
└── Building
```

### BACnet Integration

```
BACPypesApplicationMixin
    │
    ├── VAVBox (inherits)
    ├── AirHandlingUnit (inherits)
    ├── Chiller (inherits)
    ├── Boiler (inherits)
    ├── CoolingTower (inherits)
    └── Building (inherits)
```

## Component Details

### VAVBox (Variable Air Volume Box)

The VAV box is a terminal unit that controls airflow to individual zones.

**Key Features:**
- PID-controlled damper position
- Cooling/heating/deadband mode selection
- Optional reheat capability
- Zone thermal modeling with solar gains
- Occupancy-based setpoint adjustment

**Physics Model:**
```
Q_sensible = 1.08 × CFM × ΔT

Where:
- Q_sensible = Sensible cooling/heating (BTU/hr)
- CFM = Airflow rate (ft³/min)
- ΔT = Temperature difference (°F)
- 1.08 = Air constant (ρ × cp × 60)
```

**BACnet Points:**
- Zone Temperature (AI)
- Zone Temp Setpoint (AV)
- Damper Position (AV)
- Discharge Air Temp (AI)
- Current Airflow (AI)
- Mode (MSV: Heating/Cooling/Deadband)
- Occupancy (BV)

### AirHandlingUnit (AHU)

The AHU provides conditioned air to multiple VAV boxes.

**Key Features:**
- Supply air temperature control
- Supply temperature reset based on zone demands
- Chilled water or DX cooling
- Multiple VAV box management
- Fan speed control

**Control Strategy:**
1. Aggregate VAV box demands
2. Calculate required supply air temperature
3. Apply supply temperature reset if enabled
4. Update all connected VAV boxes

**BACnet Points:**
- Supply Air Temp (AI)
- Supply Air Temp Setpoint (AV)
- Mixed Air Temp (AI)
- Return Air Temp (AI)
- Total Supply Airflow (AI)
- Supply Fan Speed (AV)
- Cooling Valve Position (AV)
- Heating Valve Position (AV)

### Chiller

Water-cooled or air-cooled chiller for producing chilled water.

**Key Features:**
- Variable COP based on load and conditions
- Part-load ratio constraints
- Cooling tower integration (water-cooled)
- Condenser water temperature tracking

**Performance Model:**
```
COP = f(PLR, T_condenser, T_chw)

Where:
- PLR = Part Load Ratio (load/capacity)
- T_condenser = Condenser water temperature
- T_chw = Leaving chilled water temperature
```

**BACnet Points:**
- Leaving Chilled Water Temp (AI)
- Entering Chilled Water Temp (AI)
- Chilled Water Flow (AI)
- Current Load (AI)
- Current COP (AI)
- Compressor Power (AI)

### Boiler

Gas, electric, or propane boiler for heating hot water.

**Key Features:**
- Efficiency varies with load
- Cycling logic with minimum on/off times
- Condensing boiler option
- Fuel consumption tracking

**Efficiency Model:**
```
η = η_design × f(PLR) × f(T_return)

Where:
- η_design = Design efficiency
- f(PLR) = Part load factor
- f(T_return) = Return water temperature factor (condensing)
```

**BACnet Points:**
- Leaving Water Temp (AI)
- Entering Water Temp (AI)
- Hot Water Flow (AI)
- Current Load (AI)
- Current Efficiency (AI)
- Fuel Consumption (AI)
- Boiler Status (BV)

### CoolingTower

Evaporative cooling tower for heat rejection.

**Key Features:**
- Approach temperature calculation
- Variable speed fan control
- Multi-cell support
- Wet bulb-based performance

**Performance Model:**
```
T_leaving = T_wet_bulb + Approach

Approach = f(load, wet_bulb, flow, fan_speed)
```

**BACnet Points:**
- Leaving Water Temp (AI)
- Entering Water Temp (AI)
- Condenser Water Flow (AI)
- Fan Speed (AV)
- Current Approach (AI)
- Ambient Wet Bulb (AI)

## Configuration System

### Configuration Dataclasses

Equipment can be instantiated from configuration objects:

```python
from src.core.config import VAVConfig, ThermalZoneConfig
from src.vav_box import VAVBox

config = VAVConfig(
    name="VAV-101",
    min_airflow=100,
    max_airflow=800,
    zone_temp_setpoint=72,
    thermal_zone=ThermalZoneConfig(
        zone_area=400,
        zone_volume=3200,
        window_orientation="east"
    )
)

vav = VAVBox.from_config(config)
```

### Configuration Files

YAML or JSON configuration files can be loaded:

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

## Physics Calculations

### Thermal Module (`src/physics/thermal.py`)

```python
def calculate_sensible_cooling(cfm: float, delta_t: float) -> float:
    """Calculate sensible cooling in BTU/hr.

    Q = 1.08 × CFM × ΔT

    Args:
        cfm: Airflow in cubic feet per minute
        delta_t: Temperature difference in °F

    Returns:
        Sensible heat in BTU/hr
    """
```

### Fluid Module (`src/physics/fluid.py`)

```python
def calculate_water_heat_transfer(gpm: float, delta_t: float) -> float:
    """Calculate water heat transfer in BTU/hr.

    Q = 500 × GPM × ΔT

    Args:
        gpm: Flow rate in gallons per minute
        delta_t: Temperature difference in °F

    Returns:
        Heat transfer in BTU/hr
    """
```

## BACnet Integration

### Network Architecture

Each equipment instance can create a BACnet device with unique device ID:

```
BACnet Network (Virtual or IP)
├── VAV-101 (Device ID: 1001)
│   ├── AI:1 Zone Temperature
│   ├── AV:1 Zone Setpoint
│   └── ...
├── VAV-102 (Device ID: 1002)
├── AHU-1 (Device ID: 2001)
└── Chiller-1 (Device ID: 3001)
```

### Point Mapping

Process variables are automatically mapped to BACnet objects:

| Variable Type | BACnet Object Type |
|--------------|-------------------|
| Temperature  | Analog Input (AI) |
| Setpoint     | Analog Value (AV) |
| Status       | Binary Value (BV) |
| Mode         | Multi-State Value (MSV) |

## Testing

### Test Structure

```
tests/
├── test_vav_box.py         # VAV box unit tests
├── test_ahu.py             # AHU unit tests
├── test_chiller.py         # Chiller unit tests
├── test_boiler.py          # Boiler unit tests
├── test_cooling_tower.py   # Cooling tower unit tests
├── test_config.py          # Configuration system tests
├── test_parametrized.py    # Parametrized behavior tests
├── integration/
│   └── test_building_simulation.py  # Integration tests
└── performance/
    └── test_simulation_speed.py     # Performance benchmarks
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_vav_box.py

# Run performance tests
uv run pytest tests/performance/ -v
```

## Performance Characteristics

Based on benchmark tests:

| Operation | Time (1000 iterations) |
|-----------|----------------------|
| VAV update | < 100ms |
| AHU update (10 VAVs) | < 10ms |
| Chiller update | < 100ms |
| Boiler update | < 100ms |
| 1-hour simulation (10 VAVs) | < 100ms |
| 24-hour simulation (20 VAVs) | < 200ms |

## Extending the System

### Adding New Equipment Types

1. Create a new class inheriting from appropriate base:
   ```python
   from src.equipment.base import PlantEquipment

   class HeatPump(PlantEquipment):
       def update(self, **kwargs):
           # Implement update logic
           pass
   ```

2. Define process variables and metadata:
   ```python
   def get_process_variables(self):
       return {
           "leaving_water_temp": self.leaving_water_temp,
           "cop": self.current_cop,
       }
   ```

3. Add BACnet mixin for network exposure:
   ```python
   from src.bacnet.mixin import BACPypesApplicationMixin

   class HeatPump(PlantEquipment, BACPypesApplicationMixin):
       pass
   ```

### Adding New Control Sequences

Control sequences can be added to the `src/controls/` module:

```python
# src/controls/sequences.py

def optimal_start(
    zone_temps: dict[str, float],
    setpoints: dict[str, float],
    outdoor_temp: float,
    occupancy_time: tuple[int, int]
) -> float:
    """Calculate optimal start time for HVAC system."""
    # Implementation
    pass
```

## Dependencies

- **bacpypes3**: BACnet/IP protocol implementation
- **pyyaml**: YAML configuration file support
- **pytest**: Testing framework

## References

- ASHRAE Handbook - Fundamentals (heat transfer equations)
- ASHRAE Handbook - HVAC Systems and Equipment
- BACnet Standard (ASHRAE 135)
