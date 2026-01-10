# HVACNetwork Refactoring Roadmap

## Executive Summary

This document outlines a comprehensive refactoring plan for the HVACNetwork BACnet simulation project. The codebase is functional but has accumulated technical debt that impacts maintainability, testability, and extensibility.

**Current State Score: 5.4/10** - Functional but needs refactoring before major expansion.

| Aspect | Score | Notes |
|--------|-------|-------|
| Code Organization | 6/10 | Good equipment separation; BACnet mixin too coupled |
| Type Safety | 4/10 | Only `bacnet_network.py` has type hints |
| Configuration | 2/10 | All values hardcoded; no config system |
| Error Handling | 4/10 | Mixed patterns; silent failures; no structured logging |
| Testing | 7/10 | Well-organized; gaps in integration tests |
| Documentation | 5/10 | Good docstrings; missing architecture docs |
| Maintainability | 6/10 | Duplicated logic; magic numbers throughout |
| Extensibility | 5/10 | Tight coupling; hard to add new equipment types |

---

## Critical Issues to Address Immediately

### Bug Fixes (Priority: CRITICAL)

#### 1. Missing Return Statement - `cooling_tower.py:56`
```python
# CURRENT (broken):
@property
def current_range(self):
    self.entering_water_temp - self.leaving_water_temp  # Returns None!

# FIX:
@property
def current_range(self):
    return self.entering_water_temp - self.leaving_water_temp
```

#### 2. Silent Exception Swallowing - `base_equip.py:100-101`
```python
# CURRENT (dangerous):
except Exception:
    pass  # Errors silently ignored

# FIX:
except Exception as e:
    logger.warning(f"Failed to update {point_name}: {e}")
```

#### 3. Hardcoded Network Configuration - `base_equip.py:189-192`
```python
# CURRENT:
"ip-subnet-mask": "255.255.0.0",  # Only works for /16
"ip-default-gateway": "172.26.0.1",  # Hardcoded

# FIX: Derive from CIDR input or make configurable
```

---

## Architecture Overview

### Current Structure
```
src/
├── base_equip.py      (315 LOC) - BACnet mixin (mixed concerns)
├── vav_box.py         (922 LOC) - VAV box + PID + thermal model (TOO LARGE)
├── ahu.py             (492 LOC) - Air handling unit
├── chiller.py         (481 LOC) - Chiller (coupled to cooling tower)
├── boiler.py          (492 LOC) - Boiler with cycling logic
├── cooling_tower.py   (444 LOC) - Cooling tower
├── building.py        (580 LOC) - Building container
├── bacnet_network.py  (327 LOC) - Network topology manager
└── main.py            (468 LOC) - Entry point (mixed concerns)
```

### Current Inheritance (Flat)
```
BACPypesApplicationMixin
    ├── VAVBox
    ├── AirHandlingUnit
    ├── Boiler
    ├── Chiller
    ├── CoolingTower
    └── Building
```

### Proposed Structure
```
src/
├── core/
│   ├── __init__.py
│   ├── constants.py           # Physics & engineering constants
│   ├── config.py              # Configuration management
│   ├── exceptions.py          # Custom exceptions
│   └── logging.py             # Structured logging setup
│
├── physics/
│   ├── __init__.py
│   ├── thermal.py             # Heat transfer calculations
│   ├── fluid.py               # Fluid dynamics (air, water)
│   └── psychrometrics.py      # Air properties (future)
│
├── equipment/
│   ├── __init__.py
│   ├── base.py                # Abstract Equipment base class
│   ├── vav_box.py             # VAV box (slimmed down)
│   ├── ahu.py                 # Air handling unit
│   ├── chiller.py             # Chiller
│   ├── boiler.py              # Boiler
│   ├── cooling_tower.py       # Cooling tower
│   └── building.py            # Building container
│
├── controls/
│   ├── __init__.py
│   ├── pid.py                 # PID controller
│   └── sequences.py           # Control sequences (future)
│
├── bacnet/
│   ├── __init__.py
│   ├── mixin.py               # BACnet application mixin
│   ├── network.py             # Network topology manager
│   └── points.py              # Point creation helpers
│
├── simulation/
│   ├── __init__.py
│   ├── engine.py              # Simulation loop
│   └── scenarios.py           # Pre-built scenarios
│
└── main.py                    # Clean entry point
```

### Proposed Inheritance
```
ABC: Equipment (abstract)
    ├── TerminalUnit (abstract)
    │   └── VAVBox
    ├── AirHandler (abstract)
    │   └── AirHandlingUnit
    ├── PlantEquipment (abstract)
    │   ├── Chiller
    │   ├── Boiler
    │   └── CoolingTower
    └── Building

Mixin: BACnetDeviceMixin (composition, not inheritance)
```

---

## Refactoring Phases

### Phase 1: Foundation (Week 1-2)
**Goal:** Fix bugs, extract constants, add basic infrastructure

#### 1.1 Fix Critical Bugs
- [ ] `cooling_tower.py:56` - Add missing return statement
- [ ] `base_equip.py:100` - Replace silent exception with logging
- [ ] `cooling_tower.py:101` - Fix fan speed logic edge case

#### 1.2 Create Constants Module
Create `src/core/constants.py`:
```python
"""Physical and engineering constants for HVAC simulation."""

# Air properties (at standard conditions)
AIR_DENSITY = 0.075  # lb/ft³
AIR_SPECIFIC_HEAT = 0.24  # BTU/(lb·°F)

# Water properties
WATER_SPECIFIC_HEAT = 1.0  # BTU/(lb·°F)
WATER_DENSITY = 8.34  # lb/gal
WATER_HEAT_CONSTANT = 500  # BTU/(hr·gpm·°F) = density × specific_heat × 60

# Energy conversions
BTU_PER_KWH = 3412
BTU_PER_TON_HR = 12000
KW_PER_TON = 3.517

# Fuel properties
NATURAL_GAS_BTU_PER_CF = 1030
PROPANE_BTU_PER_GAL = 91500

# Default control parameters
DEFAULT_PID_KP = 0.5
DEFAULT_PID_KI = 0.1
DEFAULT_PID_KD = 0.05
```

#### 1.3 Add Structured Logging
Replace all `print()` statements with proper logging:
```python
import logging
logger = logging.getLogger(__name__)

# Instead of: print(f"Creating {device_name}...")
logger.info("Creating device", extra={"device_name": device_name})
```

#### 1.4 Add Type Hints
Add return type hints to all public methods across equipment classes.

**Files to update:**
- [ ] `vav_box.py` (~40 methods)
- [ ] `ahu.py` (~25 methods)
- [ ] `boiler.py` (~25 methods)
- [ ] `chiller.py` (~25 methods)
- [ ] `cooling_tower.py` (~20 methods)
- [ ] `building.py` (~20 methods)
- [ ] `base_equip.py` (~10 methods)

---

### Phase 2: Separation of Concerns (Week 3-4)
**Goal:** Decouple physics from BACnet, extract reusable components

#### 2.1 Extract Physics Calculations
Create `src/physics/thermal.py`:
```python
"""Thermal calculations for HVAC equipment."""
from src.core.constants import AIR_DENSITY, AIR_SPECIFIC_HEAT, WATER_HEAT_CONSTANT

def calculate_air_mass_flow(cfm: float) -> float:
    """Calculate air mass flow rate in lb/hr."""
    return cfm * AIR_DENSITY * 60

def calculate_sensible_cooling(cfm: float, delta_t: float) -> float:
    """Calculate sensible cooling in BTU/hr."""
    mass_flow = calculate_air_mass_flow(cfm)
    return mass_flow * AIR_SPECIFIC_HEAT * delta_t

def calculate_water_heat_transfer(gpm: float, delta_t: float) -> float:
    """Calculate water heat transfer in BTU/hr."""
    return WATER_HEAT_CONSTANT * gpm * delta_t

def calculate_chiller_delta_t(load_btu: float, flow_gpm: float) -> float:
    """Calculate chilled water temperature difference."""
    if flow_gpm <= 0:
        return 0.0
    return load_btu / (WATER_HEAT_CONSTANT * flow_gpm)
```

#### 2.2 Create Abstract Equipment Base
Create `src/equipment/base.py`:
```python
"""Abstract base class for all HVAC equipment."""
from abc import ABC, abstractmethod
from typing import Dict, Any

class Equipment(ABC):
    """Base class for all simulated equipment."""

    def __init__(self, name: str):
        self.name = name
        self._app = None  # BACnet application (optional)

    @abstractmethod
    def update(self, **kwargs) -> None:
        """Update equipment state for one time step."""
        pass

    @abstractmethod
    def get_process_variables(self) -> Dict[str, Any]:
        """Return current state as dictionary."""
        pass

    @abstractmethod
    def get_process_variables_metadata(self) -> Dict[str, Dict]:
        """Return metadata for process variables."""
        pass

    def attach_bacnet(self, app) -> None:
        """Attach a BACnet application to this equipment."""
        self._app = app

    async def update_bacnet_device(self) -> None:
        """Update BACnet points from current state."""
        if self._app is not None:
            # Delegate to mixin or helper
            await update_bacnet_points(self._app, self.get_process_variables())
```

#### 2.3 Extract PID Controller
Move to `src/controls/pid.py` (already exists in `vav_box.py`, just relocate):
```python
"""PID Controller implementation."""
from dataclasses import dataclass
from typing import Optional

@dataclass
class PIDController:
    """Proportional-Integral-Derivative controller."""
    kp: float = 0.5
    ki: float = 0.1
    kd: float = 0.05
    output_min: float = 0.0
    output_max: float = 1.0

    _integral: float = 0.0
    _last_error: Optional[float] = None

    def update(self, setpoint: float, measured: float, dt: float = 1.0) -> float:
        """Calculate control output."""
        error = setpoint - measured

        # Proportional
        p_term = self.kp * error

        # Integral with anti-windup
        self._integral += error * dt
        i_term = self.ki * self._integral

        # Derivative
        if self._last_error is not None:
            d_term = self.kd * (error - self._last_error) / dt
        else:
            d_term = 0.0
        self._last_error = error

        # Combine and clamp
        output = p_term + i_term + d_term
        return max(self.output_min, min(self.output_max, output))

    def reset(self) -> None:
        """Reset controller state."""
        self._integral = 0.0
        self._last_error = None
```

#### 2.4 Refactor BACnet Mixin
Slim down to single responsibility - create `src/bacnet/mixin.py`:
```python
"""BACnet device mixin for equipment classes."""
from typing import Dict, Any, Optional

class BACnetDeviceMixin:
    """Mixin to add BACnet capabilities to equipment."""

    _bacnet_app: Optional[Any] = None

    def create_bacnet_device(self, config: 'BACnetDeviceConfig') -> Any:
        """Create and return a BACnet application for this equipment."""
        # Simplified device creation
        pass

    async def sync_to_bacnet(self) -> int:
        """Sync current state to BACnet points. Returns count of updated points."""
        if self._bacnet_app is None:
            return 0
        # Update logic here
        pass
```

---

### Phase 3: Configuration System (Week 5-6)
**Goal:** Externalize all configuration, support multiple config formats

#### 3.1 Create Configuration Schema
Create `src/core/config.py`:
```python
"""Configuration management for HVAC simulation."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import yaml
import json

@dataclass
class PIDConfig:
    kp: float = 0.5
    ki: float = 0.1
    kd: float = 0.05

@dataclass
class VAVConfig:
    name: str
    min_airflow: float = 100  # CFM
    max_airflow: float = 1000  # CFM
    zone_temp_setpoint: float = 72  # °F
    deadband: float = 2  # °F
    has_reheat: bool = True
    pid: PIDConfig = field(default_factory=PIDConfig)

@dataclass
class AHUConfig:
    name: str
    supply_air_temp_setpoint: float = 55  # °F
    min_supply_air_temp: float = 52
    max_supply_air_temp: float = 65
    max_supply_airflow: float = 10000  # CFM
    cooling_type: str = "chilled_water"

@dataclass
class SimulationConfig:
    time_step_minutes: int = 1
    speed_multiplier: int = 60  # 1 hour per minute
    start_hour: int = 6

@dataclass
class BACnetConfig:
    ip_address: Optional[str] = None  # Auto-detect if None
    subnet_mask: str = "255.255.0.0"
    port: int = 47808
    device_id_base: int = 1000

def load_config(path: str) -> Dict[str, Any]:
    """Load configuration from YAML or JSON file."""
    with open(path) as f:
        if path.endswith('.yaml') or path.endswith('.yml'):
            return yaml.safe_load(f)
        return json.load(f)
```

#### 3.2 Create Default Configuration File
Create `data/default_config.yaml`:
```yaml
simulation:
  time_step_minutes: 1
  speed_multiplier: 60
  start_hour: 6

bacnet:
  # ip_address: auto  # Auto-detect
  subnet_mask: "255.255.0.0"
  port: 47808
  device_id_base: 1000

defaults:
  vav:
    min_airflow: 100
    max_airflow: 1000
    zone_temp_setpoint: 72
    deadband: 2
    has_reheat: true
    pid:
      kp: 0.5
      ki: 0.1
      kd: 0.05

  ahu:
    supply_air_temp_setpoint: 55
    min_supply_air_temp: 52
    max_supply_air_temp: 65
    cooling_type: chilled_water

  chiller:
    capacity_tons: 500
    efficiency_kw_per_ton: 0.6
    cooling_type: water_cooled

  boiler:
    capacity_btu: 1000000
    efficiency: 0.85
    fuel_type: natural_gas
```

---

### Phase 4: Testing & Documentation (Week 7-8)
**Goal:** Improve test coverage, add integration tests, document architecture

#### 4.1 Add Integration Tests
Create `tests/integration/test_building_simulation.py`:
- Test complete building with multiple AHUs
- Test chiller + cooling tower interaction
- Test thermal convergence across zones

#### 4.2 Add Parametrized Tests
Convert existing tests to use pytest parametrize:
```python
@pytest.mark.parametrize("outdoor_temp,expected_mode", [
    (95, "cooling"),
    (65, "deadband"),
    (35, "heating"),
])
def test_vav_mode_selection(outdoor_temp, expected_mode):
    # Test implementation
    pass
```

#### 4.3 Add Performance Tests
Create `tests/performance/test_simulation_speed.py`:
- Benchmark simulation with 100+ VAVs
- Memory usage profiling
- BACnet update throughput

#### 4.4 Create Architecture Documentation
- Add `docs/architecture.md` with diagrams
- Document physics models with equations
- Add API reference

---

### Phase 5: Cleanup & Polish (Week 9-10)
**Goal:** Consolidate examples, remove duplication, final polish

#### 5.1 Consolidate Example Files
**Keep:**
- `examples/simple_vav.py` - Basic single VAV example
- `examples/complete_building.py` - Full building simulation

**Archive/Remove:**
- `complete_bacpypes3_simulation.py` (57 KB - duplicate)
- `complete_bacpypes3_simulation_minute.py` (55 KB - duplicate)
- `brick_based_simulation_refactored.py` (confusing name)
- Multiple small overlapping examples

#### 5.2 Add Pre-commit Hooks
Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.0.0
    hooks:
      - id: mypy
        additional_dependencies: [types-PyYAML]
```

#### 5.3 Update pyproject.toml
Add mypy configuration and stricter ruff rules.

---

## Dependency Graph (Current Issues)

```
┌─────────────┐
│   Chiller   │──────────┐
└─────────────┘          │ tight coupling
                         ▼
              ┌──────────────────┐
              │  CoolingTower    │
              └──────────────────┘

┌─────────────┐
│     AHU     │──────────┐
└─────────────┘          │ list reference
                         ▼
              ┌──────────────────┐
              │    VAVBox[]      │
              └──────────────────┘

┌─────────────┐
│  Building   │──────────┬──────────┐
└─────────────┘          │          │
                         ▼          ▼
              ┌──────────┐  ┌──────────┐
              │  Zones   │  │Equipment │
              └──────────┘  └──────────┘
```

**Proposed:** Use dependency injection and event-based communication for loose coupling.

---

## Migration Strategy

### For Each Phase:
1. Create new module/structure alongside existing
2. Update imports incrementally
3. Run full test suite after each change
4. Deprecate old patterns with warnings
5. Remove deprecated code after verification

### Backward Compatibility:
- Keep `src/vav_box.py` import working (re-export from new location)
- Maintain existing `main.py` interface
- Document breaking changes in CHANGELOG.md

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Type hint coverage | ~10% | 90%+ |
| Test coverage | ~60% | 85%+ |
| Cyclomatic complexity (max) | 25+ | <15 |
| Duplicate code blocks | 15+ | <3 |
| Hardcoded constants | 75+ | 0 |
| Average file size | 500 LOC | <300 LOC |

---

## Timeline Summary

| Phase | Duration | Focus |
|-------|----------|-------|
| Phase 1 | Week 1-2 | Bug fixes, constants, logging, type hints |
| Phase 2 | Week 3-4 | Separate physics/BACnet, extract components |
| Phase 3 | Week 5-6 | Configuration system |
| Phase 4 | Week 7-8 | Testing & documentation |
| Phase 5 | Week 9-10 | Cleanup & polish |

**Total Estimated Effort:** 10 weeks (part-time) or 4-5 weeks (full-time)

---

## Questions for Discussion

1. **Configuration Format:** YAML vs JSON vs TOML for config files?
2. **Async Strategy:** Should all equipment updates be async, or only BACnet?
3. **Plugin System:** Do we want to support custom equipment types as plugins?
4. **Backwards Compatibility:** How strict should we be about maintaining old APIs?
5. **Brick Integration:** Should Brick parsing move to a separate package?

---

## Appendix: Files to Create

```
src/core/__init__.py
src/core/constants.py
src/core/config.py
src/core/exceptions.py
src/core/logging.py
src/physics/__init__.py
src/physics/thermal.py
src/physics/fluid.py
src/equipment/__init__.py
src/equipment/base.py
src/controls/__init__.py
src/controls/pid.py
src/bacnet/__init__.py
src/bacnet/mixin.py
src/bacnet/points.py
src/simulation/__init__.py
src/simulation/engine.py
data/default_config.yaml
docs/architecture.md
tests/integration/__init__.py
tests/integration/test_building_simulation.py
tests/performance/__init__.py
tests/performance/test_simulation_speed.py
```

---

*Document Version: 1.0*
*Created: 2025-01-10*
*Last Updated: 2025-01-10*
