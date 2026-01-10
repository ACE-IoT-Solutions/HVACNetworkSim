"""
Physical and engineering constants for HVAC simulation.

This module centralizes all magic numbers and physical constants used throughout
the simulation. Values are based on standard conditions (sea level, 70°F) unless
otherwise noted.

Usage:
    from src.core.constants import AIR_DENSITY, AIR_SPECIFIC_HEAT

    mass_flow = cfm * AIR_DENSITY * 60  # lb/hr
    heat = mass_flow * AIR_SPECIFIC_HEAT * delta_t  # BTU/hr
"""

# =============================================================================
# Air Properties (at standard conditions: 70°F, sea level)
# =============================================================================

AIR_DENSITY: float = 0.075  # lb/ft³ - density of air
AIR_SPECIFIC_HEAT: float = 0.24  # BTU/(lb·°F) - specific heat of air at constant pressure

# =============================================================================
# Water Properties
# =============================================================================

WATER_SPECIFIC_HEAT: float = 1.0  # BTU/(lb·°F) - specific heat of water
WATER_DENSITY: float = 8.34  # lb/gal - density of water at ~60°F

# Combined water heat transfer constant: density × specific_heat × 60 min/hr
# Used in: Q = 500 × GPM × ΔT (BTU/hr)
WATER_HEAT_CONSTANT: float = 500.0  # BTU/(hr·gpm·°F)

# =============================================================================
# Energy Conversions
# =============================================================================

BTU_PER_KWH: float = 3412.0  # BTU per kilowatt-hour
BTU_PER_TON_HR: float = 12000.0  # BTU/hr per ton of refrigeration
KW_PER_TON: float = 3.517  # kW per ton of refrigeration (theoretical minimum)

# =============================================================================
# Fuel Properties
# =============================================================================

NATURAL_GAS_BTU_PER_CF: float = 1030.0  # BTU per cubic foot of natural gas
PROPANE_BTU_PER_GAL: float = 91500.0  # BTU per gallon of propane
FUEL_OIL_BTU_PER_GAL: float = 138500.0  # BTU per gallon of #2 fuel oil

# =============================================================================
# Thermal Properties
# =============================================================================

# Condensing threshold for high-efficiency boilers
CONDENSING_THRESHOLD_TEMP: float = 130.0  # °F - return water temp below which condensing occurs

# Typical approach temperatures
CHILLER_APPROACH_TEMP: float = 5.0  # °F - typical evaporator approach
COOLING_TOWER_APPROACH_MIN: float = 5.0  # °F - minimum practical approach to wet bulb

# =============================================================================
# Control Parameters (Defaults)
# =============================================================================

DEFAULT_PID_KP: float = 0.5  # Proportional gain
DEFAULT_PID_KI: float = 0.1  # Integral gain
DEFAULT_PID_KD: float = 0.05  # Derivative gain

# Temperature deadbands
DEFAULT_ZONE_DEADBAND: float = 2.0  # °F - typical zone temperature deadband
DEFAULT_SUPPLY_DEADBAND: float = 1.0  # °F - supply air temperature deadband

# =============================================================================
# BACnet Protocol Constants
# =============================================================================

BACNET_DEFAULT_PORT: int = 47808  # Standard BACnet/IP UDP port
BACNET_VENDOR_ID: int = 999  # ACE IoT Solutions vendor ID
BACNET_VENDOR_NAME: str = "ACEHVACNetwork"

# Device configuration defaults
BACNET_MAX_APDU_LENGTH: int = 1024
BACNET_PROTOCOL_VERSION: int = 1
BACNET_PROTOCOL_REVISION: int = 22

# =============================================================================
# Simulation Defaults
# =============================================================================

DEFAULT_OUTDOOR_TEMP: float = 70.0  # °F - default outdoor temperature
DEFAULT_ZONE_TEMP: float = 72.0  # °F - default zone temperature
DEFAULT_SUPPLY_AIR_TEMP: float = 55.0  # °F - typical cooling supply air temp

# Time constants
SIMULATION_TIME_STEP_MINUTES: int = 1  # Default simulation time step
BACNET_UPDATE_DELAY_SECONDS: float = 0.05  # Delay between BACnet updates

# =============================================================================
# Equipment Sizing Constants
# =============================================================================

# Safety factors for equipment sizing
AIRFLOW_SAFETY_FACTOR: float = 1.2  # 20% oversizing for airflow
CAPACITY_SAFETY_FACTOR: float = 1.1  # 10% oversizing for heating/cooling

# Typical equipment parameters
TYPICAL_FAN_EFFICIENCY: float = 0.65  # Fan motor efficiency
TYPICAL_PUMP_EFFICIENCY: float = 0.70  # Pump efficiency
TYPICAL_MOTOR_EFFICIENCY: float = 0.90  # Motor efficiency
