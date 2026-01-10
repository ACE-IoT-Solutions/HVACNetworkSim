"""Core utilities and constants for HVAC simulation."""

from src.core.config import (
    # Config dataclasses
    PIDConfig,
    ThermalZoneConfig,
    VAVConfig,
    AHUConfig,
    ChillerConfig,
    CoolingTowerConfig,
    BoilerConfig,
    BACnetConfig,
    SimulationConfig,
    BuildingConfig,
    # Config utilities
    load_config,
    save_config,
    get_default_config,
)
from src.core.constants import (
    # Air properties
    AIR_DENSITY,
    AIR_SPECIFIC_HEAT,
    # Water properties
    WATER_SPECIFIC_HEAT,
    WATER_DENSITY,
    WATER_HEAT_CONSTANT,
    # Energy conversions
    BTU_PER_KWH,
    BTU_PER_TON_HR,
    KW_PER_TON,
    # Fuel properties
    NATURAL_GAS_BTU_PER_CF,
    PROPANE_BTU_PER_GAL,
    # Control defaults
    DEFAULT_PID_KP,
    DEFAULT_PID_KI,
    DEFAULT_PID_KD,
    # BACnet defaults
    BACNET_DEFAULT_PORT,
    BACNET_VENDOR_ID,
    BACNET_VENDOR_NAME,
)

__all__ = [
    # Config dataclasses
    "PIDConfig",
    "ThermalZoneConfig",
    "VAVConfig",
    "AHUConfig",
    "ChillerConfig",
    "CoolingTowerConfig",
    "BoilerConfig",
    "BACnetConfig",
    "SimulationConfig",
    "BuildingConfig",
    # Config utilities
    "load_config",
    "save_config",
    "get_default_config",
    # Air properties
    "AIR_DENSITY",
    "AIR_SPECIFIC_HEAT",
    # Water properties
    "WATER_SPECIFIC_HEAT",
    "WATER_DENSITY",
    "WATER_HEAT_CONSTANT",
    # Energy conversions
    "BTU_PER_KWH",
    "BTU_PER_TON_HR",
    "KW_PER_TON",
    # Fuel properties
    "NATURAL_GAS_BTU_PER_CF",
    "PROPANE_BTU_PER_GAL",
    # Control defaults
    "DEFAULT_PID_KP",
    "DEFAULT_PID_KI",
    "DEFAULT_PID_KD",
    # BACnet defaults
    "BACNET_DEFAULT_PORT",
    "BACNET_VENDOR_ID",
    "BACNET_VENDOR_NAME",
]
