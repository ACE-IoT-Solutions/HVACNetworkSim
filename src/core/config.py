"""
Configuration management for HVAC simulation.

This module provides typed configuration dataclasses for all equipment
and simulation parameters, with support for loading from YAML or JSON files.

Usage:
    from src.core.config import (
        SimulationConfig,
        BACnetConfig,
        VAVConfig,
        AHUConfig,
        ChillerConfig,
        BoilerConfig,
        load_config,
    )

    # Load from file
    config = load_config("config.yaml")

    # Or use defaults
    vav_config = VAVConfig(name="VAV-101")
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json
import logging

logger = logging.getLogger(__name__)

# Try to import yaml, but make it optional
try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None


@dataclass
class PIDConfig:
    """Configuration for a PID controller."""

    kp: float = 0.5
    ki: float = 0.1
    kd: float = 0.05
    output_min: float = 0.0
    output_max: float = 1.0
    deadband: float = 0.5
    integral_limit: float = 10.0


@dataclass
class ThermalZoneConfig:
    """Configuration for a thermal zone."""

    zone_area: float = 400.0  # sq ft
    zone_volume: float = 3200.0  # cu ft
    window_area: float = 80.0  # sq ft
    window_orientation: str = "east"
    thermal_mass: float = 2.0  # multiplier


@dataclass
class VAVConfig:
    """Configuration for a VAV box."""

    name: str
    min_airflow: float = 100.0  # CFM
    max_airflow: float = 1000.0  # CFM
    zone_temp_setpoint: float = 72.0  # °F
    deadband: float = 2.0  # °F
    discharge_air_temp_setpoint: float = 55.0  # °F
    has_reheat: bool = True
    cooling_pid: PIDConfig = field(default_factory=PIDConfig)
    heating_pid: PIDConfig = field(default_factory=PIDConfig)
    thermal_zone: Optional[ThermalZoneConfig] = None


@dataclass
class AHUConfig:
    """Configuration for an Air Handling Unit."""

    name: str
    supply_air_temp_setpoint: float = 55.0  # °F
    min_supply_air_temp: float = 52.0  # °F
    max_supply_air_temp: float = 65.0  # °F
    max_supply_airflow: float = 10000.0  # CFM
    cooling_type: str = "chilled_water"  # or "dx"
    compressor_stages: int = 2  # for DX cooling
    chilled_water_delta_t: float = 10.0  # °F
    enable_supply_temp_reset: bool = True
    cooling_pid: PIDConfig = field(default_factory=PIDConfig)
    heating_pid: PIDConfig = field(default_factory=PIDConfig)


@dataclass
class ChillerConfig:
    """Configuration for a chiller."""

    name: str
    cooling_type: str = "water_cooled"  # or "air_cooled"
    capacity: float = 500.0  # tons
    design_cop: float = 5.0
    design_entering_condenser_temp: float = 85.0  # °F
    design_leaving_chilled_water_temp: float = 44.0  # °F
    min_part_load_ratio: float = 0.1
    design_chilled_water_flow: float = 1000.0  # GPM
    design_condenser_water_flow: Optional[float] = None  # GPM, for water-cooled


@dataclass
class CoolingTowerConfig:
    """Configuration for a cooling tower."""

    name: str
    capacity: float = 600.0  # tons
    design_approach: float = 7.0  # °F
    design_range: float = 10.0  # °F
    design_wet_bulb: float = 78.0  # °F
    design_water_flow: float = 1500.0  # GPM
    min_water_temp: float = 65.0  # °F
    max_fan_power: float = 50.0  # kW
    min_speed: float = 20.0  # percent
    tower_type: str = "counterflow"  # or "crossflow"
    num_cells: int = 1


@dataclass
class BoilerConfig:
    """Configuration for a boiler."""

    name: str
    fuel_type: str = "gas"  # or "electric" (gas includes natural_gas and propane)
    capacity: float = 1000.0  # MBH (thousand BTU/hr)
    design_efficiency: float = 0.85
    min_part_load_ratio: float = 0.2
    design_leaving_water_temp: float = 180.0  # °F
    design_entering_water_temp: float = 160.0  # °F
    design_hot_water_flow: float = 100.0  # GPM
    min_on_time: float = 5.0  # minutes
    min_off_time: float = 5.0  # minutes
    condensing: bool = False  # Condensing type (for gas boilers)
    turndown_ratio: float = 4.0  # Turndown ratio


@dataclass
class BACnetConfig:
    """Configuration for BACnet networking."""

    ip_address: Optional[str] = None  # Auto-detect if None
    subnet_mask: str = "255.255.0.0"
    gateway: str = "172.26.0.1"
    port: int = 47808
    device_id_base: int = 1000
    vendor_id: int = 999
    vendor_name: str = "ACEHVACNetwork"


@dataclass
class SimulationConfig:
    """Configuration for the simulation engine."""

    time_step_minutes: int = 1
    speed_multiplier: int = 60  # 1 hour per minute
    start_hour: int = 6
    occupied_hours: List[tuple] = field(default_factory=lambda: [(8, 18)])
    default_occupancy: int = 5


@dataclass
class BuildingConfig:
    """Complete building configuration."""

    name: str = "Default Building"
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    bacnet: BACnetConfig = field(default_factory=BACnetConfig)
    vavs: List[VAVConfig] = field(default_factory=list)
    ahus: List[AHUConfig] = field(default_factory=list)
    chillers: List[ChillerConfig] = field(default_factory=list)
    boilers: List[BoilerConfig] = field(default_factory=list)
    cooling_towers: List[CoolingTowerConfig] = field(default_factory=list)


def load_config(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load configuration from a YAML or JSON file.

    Args:
        path: Path to the configuration file

    Returns:
        Dictionary of configuration values

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file format is not supported
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, "r") as f:
        if path.suffix in (".yaml", ".yml"):
            if not YAML_AVAILABLE:
                raise ImportError(
                    "PyYAML is required for YAML config files. " "Install with: pip install pyyaml"
                )
            return yaml.safe_load(f)
        elif path.suffix == ".json":
            return json.load(f)
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")


def save_config(config: Dict[str, Any], path: Union[str, Path]) -> None:
    """
    Save configuration to a YAML or JSON file.

    Args:
        config: Configuration dictionary
        path: Path to save the file
    """
    path = Path(path)

    with open(path, "w") as f:
        if path.suffix in (".yaml", ".yml"):
            if not YAML_AVAILABLE:
                raise ImportError(
                    "PyYAML is required for YAML config files. " "Install with: pip install pyyaml"
                )
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        elif path.suffix == ".json":
            json.dump(config, f, indent=2)
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")


def config_to_dict(config: Any) -> Dict[str, Any]:
    """
    Convert a dataclass config to a dictionary.

    Args:
        config: A dataclass instance

    Returns:
        Dictionary representation
    """
    from dataclasses import asdict

    return asdict(config)


def create_vav_config(data: Dict[str, Any]) -> VAVConfig:
    """Create a VAVConfig from a dictionary."""
    # Handle nested configs
    if "cooling_pid" in data and isinstance(data["cooling_pid"], dict):
        data["cooling_pid"] = PIDConfig(**data["cooling_pid"])
    if "heating_pid" in data and isinstance(data["heating_pid"], dict):
        data["heating_pid"] = PIDConfig(**data["heating_pid"])
    if "thermal_zone" in data and isinstance(data["thermal_zone"], dict):
        data["thermal_zone"] = ThermalZoneConfig(**data["thermal_zone"])
    return VAVConfig(**data)


def create_ahu_config(data: Dict[str, Any]) -> AHUConfig:
    """Create an AHUConfig from a dictionary."""
    if "cooling_pid" in data and isinstance(data["cooling_pid"], dict):
        data["cooling_pid"] = PIDConfig(**data["cooling_pid"])
    if "heating_pid" in data and isinstance(data["heating_pid"], dict):
        data["heating_pid"] = PIDConfig(**data["heating_pid"])
    return AHUConfig(**data)


def create_chiller_config(data: Dict[str, Any]) -> ChillerConfig:
    """Create a ChillerConfig from a dictionary."""
    return ChillerConfig(**data)


def create_boiler_config(data: Dict[str, Any]) -> BoilerConfig:
    """Create a BoilerConfig from a dictionary."""
    return BoilerConfig(**data)


def get_default_config() -> BuildingConfig:
    """Get a default building configuration for testing."""
    return BuildingConfig(
        name="Default Building",
        simulation=SimulationConfig(),
        bacnet=BACnetConfig(),
    )
