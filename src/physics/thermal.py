"""
Thermal calculations for HVAC simulation.

This module provides fundamental heat transfer calculations used throughout
the HVAC simulation. All calculations use consistent units:
- Temperature: °F
- Airflow: CFM (cubic feet per minute)
- Water flow: GPM (gallons per minute)
- Heat: BTU/hr
- Power: kW

Usage:
    from src.physics.thermal import calculate_sensible_heat, calculate_air_mass_flow

    mass_flow = calculate_air_mass_flow(cfm=1000)
    heat = calculate_sensible_heat(cfm=1000, delta_t=20)
"""

from src.core.constants import (
    AIR_DENSITY,
    AIR_SPECIFIC_HEAT,
    WATER_HEAT_CONSTANT,
    BTU_PER_KWH,
)


def calculate_air_mass_flow(cfm: float) -> float:
    """
    Calculate air mass flow rate from volumetric flow.

    Args:
        cfm: Volumetric air flow in cubic feet per minute

    Returns:
        Mass flow rate in lb/hr

    Example:
        >>> calculate_air_mass_flow(1000)
        4500.0  # 1000 CFM * 0.075 lb/ft³ * 60 min/hr
    """
    return cfm * AIR_DENSITY * 60  # CFM → ft³/hr → lb/hr


def calculate_sensible_heat(cfm: float, delta_t: float) -> float:
    """
    Calculate sensible heat transfer for air.

    Uses the formula: Q = m * Cp * ΔT
    where m is mass flow rate (lb/hr) and Cp is specific heat (BTU/lb·°F)

    Args:
        cfm: Volumetric air flow in cubic feet per minute
        delta_t: Temperature difference in °F

    Returns:
        Sensible heat in BTU/hr

    Example:
        >>> calculate_sensible_heat(1000, 20)
        21600.0  # 1000 CFM @ 20°F ΔT
    """
    mass_flow = calculate_air_mass_flow(cfm)
    return mass_flow * AIR_SPECIFIC_HEAT * delta_t


def calculate_water_heat_transfer(gpm: float, delta_t: float) -> float:
    """
    Calculate heat transfer for water flow.

    Uses the standard HVAC formula: Q = 500 × GPM × ΔT
    where 500 = water density × specific heat × 60 min/hr

    Args:
        gpm: Water flow rate in gallons per minute
        delta_t: Temperature difference in °F

    Returns:
        Heat transfer in BTU/hr

    Example:
        >>> calculate_water_heat_transfer(100, 10)
        500000.0  # 100 GPM @ 10°F ΔT
    """
    return WATER_HEAT_CONSTANT * gpm * delta_t


def calculate_chilled_water_delta_t(load_btu: float, flow_gpm: float) -> float:
    """
    Calculate chilled water temperature difference from load and flow.

    Inverse of the water heat transfer equation:
    ΔT = Q / (500 × GPM)

    Args:
        load_btu: Cooling load in BTU/hr
        flow_gpm: Water flow rate in GPM

    Returns:
        Temperature difference in °F

    Raises:
        ValueError: If flow_gpm is zero or negative
    """
    if flow_gpm <= 0:
        return 0.0
    return load_btu / (WATER_HEAT_CONSTANT * flow_gpm)


def calculate_chilled_water_flow(load_btu: float, delta_t: float) -> float:
    """
    Calculate required chilled water flow from load and delta T.

    GPM = Q / (500 × ΔT)

    Args:
        load_btu: Cooling load in BTU/hr
        delta_t: Desired temperature difference in °F

    Returns:
        Required water flow in GPM

    Raises:
        ValueError: If delta_t is zero or negative
    """
    if delta_t <= 0:
        return 0.0
    return load_btu / (WATER_HEAT_CONSTANT * delta_t)


def calculate_fan_power(
    current_flow: float, max_flow: float, design_power_kw: float, min_power_fraction: float = 0.3
) -> float:
    """
    Calculate fan power using fan affinity laws.

    Fan affinity law: Power ∝ (Flow)³
    This models variable frequency drive (VFD) controlled fans.

    Args:
        current_flow: Current airflow in CFM
        max_flow: Maximum (design) airflow in CFM
        design_power_kw: Fan power at design flow in kW
        min_power_fraction: Minimum power fraction when flow is zero (default 0.3)

    Returns:
        Current fan power in kW

    Example:
        >>> calculate_fan_power(500, 1000, 10.0)
        1.25  # 50% flow → 12.5% power → 1.25 kW
    """
    if max_flow <= 0:
        return 0.0

    if current_flow <= 0:
        return 0.0

    flow_ratio = min(current_flow / max_flow, 1.0)
    # Fan affinity: Power = (Flow ratio)^3
    power_ratio = flow_ratio**3
    # Apply minimum power floor
    power_ratio = max(power_ratio, min_power_fraction * flow_ratio if flow_ratio > 0 else 0)

    return design_power_kw * power_ratio


def convert_kw_to_btu(kw: float) -> float:
    """
    Convert kilowatts to BTU/hr.

    Args:
        kw: Power in kilowatts

    Returns:
        Power in BTU/hr
    """
    return kw * BTU_PER_KWH


def convert_btu_to_kw(btu: float) -> float:
    """
    Convert BTU/hr to kilowatts.

    Args:
        btu: Power in BTU/hr

    Returns:
        Power in kilowatts
    """
    return btu / BTU_PER_KWH
