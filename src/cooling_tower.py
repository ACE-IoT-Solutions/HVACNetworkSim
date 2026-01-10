import logging
import math
from typing import TYPE_CHECKING, Any, Dict

from .base_equip import BACPypesApplicationMixin

if TYPE_CHECKING:
    from src.core.config import CoolingTowerConfig

logger = logging.getLogger(__name__)


class CoolingTower(BACPypesApplicationMixin):
    """
    Cooling Tower class that models the performance of an evaporative cooling tower
    used to reject heat from water-cooled chillers.
    """

    @classmethod
    def from_config(cls, config: "CoolingTowerConfig") -> "CoolingTower":
        """Create a CoolingTower from a CoolingTowerConfig dataclass.

        Args:
            config: CoolingTowerConfig dataclass with cooling tower parameters

        Returns:
            A new CoolingTower instance
        """
        from src.core.config import CoolingTowerConfig  # Import here to avoid circular imports

        if not isinstance(config, CoolingTowerConfig):
            raise TypeError(f"Expected CoolingTowerConfig, got {type(config).__name__}")

        return cls(
            name=config.name,
            capacity=config.capacity,
            design_approach=config.design_approach,
            design_range=config.design_range,
            design_wet_bulb=config.design_wet_bulb,
            min_speed=config.min_speed,
            tower_type=config.tower_type,
            fan_power=config.max_fan_power,
            num_cells=config.num_cells,
        )

    def __init__(
        self,
        name: str,
        capacity: float,
        design_approach: float,
        design_range: float,
        design_wet_bulb: float,
        min_speed: float,
        tower_type: str,
        fan_power: float,
        num_cells: int,
    ) -> None:
        """
        Initialize Cooling Tower with specified parameters.

        Args:
            name: Name of the cooling tower
            capacity: Nominal cooling capacity in tons
            design_approach: Design approach temperature (LWT - WB) in °F
            design_range: Design range temperature (EWT - LWT) in °F
            design_wet_bulb: Design wet bulb temperature in °F
            min_speed: Minimum fan speed in percent
            tower_type: Type of tower ("counterflow" or "crossflow")
            fan_power: Fan power at 100% speed in kW
            num_cells: Number of cells in the cooling tower
        """
        # Design parameters
        self.name = name
        self.capacity = capacity
        self.design_approach = design_approach
        self.design_range = design_range
        self.design_wet_bulb = design_wet_bulb
        self.min_speed = min_speed
        self.tower_type = tower_type.lower()
        self.fan_power = fan_power
        self.num_cells = num_cells

        # Current state
        self.current_load: float = 0.0  # Current heat rejection load in tons
        self.entering_water_temp: float = 95.0  # Default entering water temperature in °F
        self.leaving_water_temp: float = 85.0  # Default leaving water temperature in °F
        self.current_wet_bulb: float = design_wet_bulb  # Current ambient wet bulb temperature in °F
        self.fan_speed: float = 0.0  # Current fan speed in percent
        self.water_flow: float = 0.0  # Current water flow in GPM

        # Calculated parameters
        self.design_flow: float = 3.0 * capacity  # Rule of thumb: 3 GPM/ton
        self.current_approach: float = design_approach

        # Energy tracking
        self.energy_consumption: float = 0.0  # kWh

    @property
    def current_range(self) -> float:
        """Temperature difference between entering and leaving water (°F)."""
        return self.entering_water_temp - self.leaving_water_temp

    @property
    def outdoor_wet_bulb(self) -> float:
        return self.current_wet_bulb

    @property
    def condenser_water_supply_temp(self) -> float:
        return self.leaving_water_temp

    @property
    def condenser_water_return_temp(self) -> float:
        return self.entering_water_temp

    def update_load(
        self,
        load: float,
        entering_water_temp: float,
        ambient_wet_bulb: float,
        condenser_water_flow: float,
        auto_adjust_fan: bool = True,
    ) -> None:
        """
        Update cooling tower with new load and conditions.

        Args:
            load: Current heat rejection load in tons
            entering_water_temp: Entering water temperature in °F
            ambient_wet_bulb: Ambient wet bulb temperature in °F
            condenser_water_flow: Condenser water flow rate in GPM
            auto_adjust_fan: Whether to automatically adjust fan speed (default: True)
        """
        # Limit load to capacity
        self.current_load = min(load, self.capacity)
        self.entering_water_temp = entering_water_temp
        self.current_wet_bulb = ambient_wet_bulb
        self.water_flow = condenser_water_flow

        # Calculate required approach temperature based on load and conditions
        required_approach = self._calculate_required_approach()
        self.current_approach = required_approach

        # Calculate leaving water temperature
        self.leaving_water_temp = self.current_wet_bulb + required_approach

        # Adjust fan speed if auto control is enabled
        if auto_adjust_fan:
            self._adjust_fan_speed()

    def set_fan_speed(self, speed: float) -> None:
        """Set fan speed manually."""
        # Ensure speed is between min_speed and 100%
        self.fan_speed = max(min(speed, 100), 0 if self.current_load == 0 else self.min_speed)

    def calculate_approach(self) -> float:
        """Calculate current approach temperature (LWT - WB)."""
        return self.leaving_water_temp - self.current_wet_bulb

    def calculate_range(self) -> float:
        """Calculate current range temperature (EWT - LWT)."""
        return self.entering_water_temp - self.leaving_water_temp

    def calculate_efficiency(self) -> float:
        """Calculate cooling tower efficiency based on approach temperature."""
        if self.current_load == 0:
            return 0

        # Calculate actual range
        actual_range = self.calculate_range()

        # Calculate theoretical maximum range (EWT - WB)
        max_range = self.entering_water_temp - self.current_wet_bulb

        if max_range <= 0:
            return 1.0  # Avoid division by zero

        # Efficiency = Actual Range / Ideal Range
        efficiency = actual_range / max_range

        # Limit to 0-1 range
        return max(0, min(1, efficiency))

    def calculate_power_consumption(self) -> float:
        """Calculate current power consumption in kW."""
        if self.current_load == 0 or self.fan_speed == 0:
            return 0

        # Fan power follows cube law: Power ∝ (Speed)³
        power_factor = (self.fan_speed / 100) ** 3

        # Total power is proportional to number of active cells
        active_cells = self._calculate_active_cells()
        cell_power = self.fan_power / self.num_cells

        return power_factor * cell_power * active_cells

    def calculate_energy_consumption(self, hours: float = 1) -> float:
        """Calculate energy consumption in kWh for a specified duration."""
        power_kw = self.calculate_power_consumption()
        energy_kwh = power_kw * hours

        return energy_kwh

    def calculate_water_consumption(self) -> float:
        """Calculate water consumption in gallons per hour."""
        if self.current_load == 0:
            return 0

        # Standard rule of thumb for tower water consumption is approximately
        # 2 gallons per minute per 100 tons of cooling
        tonnage_factor = self.current_load / 100  # Divide by 100 tons
        base_gpm = 2 * tonnage_factor

        # Adjust for range temperature
        range_temp = self.calculate_range()
        range_factor = range_temp / 10.0  # Normalized to 10°F range

        # Evaporation is approximately 1 gallon per minute per 100 tons per 10°F range
        evaporation_gpm = base_gpm * range_factor

        # Add drift (0.1-0.2% of circulating water flow)
        drift_gpm = 0.001 * self.water_flow

        # Add blowdown (depends on cycles of concentration, typically 3)
        blowdown_gpm = evaporation_gpm / 3

        # Total water consumption in gallons per hour
        total_water_gph = (evaporation_gpm + drift_gpm + blowdown_gpm) * 60

        return total_water_gph

    def _calculate_required_approach(self) -> float:
        """Calculate required approach temperature based on current conditions."""
        # Base approach at design conditions
        base_approach = self.design_approach

        # Adjust for load factor
        load_factor = self.current_load / self.capacity
        if load_factor > 1:
            # Overloaded condition - approach increases rapidly
            approach_load_factor = 1 + 3 * (load_factor - 1) ** 2
        else:
            # Normal load - approach improves at part load
            approach_load_factor = 0.7 + 0.3 * load_factor**2

        # Adjust for wet bulb deviation
        wb_deviation = self.current_wet_bulb - self.design_wet_bulb
        wb_factor = 1 + 0.02 * wb_deviation  # 2% change per °F deviation

        # Adjust for flow factor
        flow_factor = 1
        if self.water_flow > 0 and self.design_flow > 0:
            design_flow_ratio = self.water_flow / self.design_flow
            flow_factor = design_flow_ratio**-0.6  # Flow impact on approach

        # Calculate final approach
        approach = base_approach * approach_load_factor * wb_factor * flow_factor

        # Apply minimum approach limit (can't go below ~1°F in practical towers)
        return max(1, approach)

    def _adjust_fan_speed(self) -> None:
        """Adjust fan speed based on required approach and current conditions."""
        # Calculate target approach based on load and wet bulb
        target_approach = self._calculate_required_approach()

        # Calculate required fan speed to achieve target approach
        # At low loads, we can run at low speeds
        load_ratio = self.current_load / self.capacity

        # Base fan speed on load ratio
        base_speed = 100 * load_ratio**0.5

        # Adjust based on wet bulb vs. design
        wb_factor = 1 + 0.02 * (self.design_wet_bulb - self.current_wet_bulb)

        # Higher speed if current approach is too high
        current_approach = self.leaving_water_temp - self.current_wet_bulb
        approach_factor = 1
        if current_approach > target_approach:
            approach_factor = 1 + 0.1 * (current_approach - target_approach)

        # Calculate target fan speed
        target_speed = base_speed * wb_factor * approach_factor

        # Ensure minimum speed when tower is loaded
        if self.current_load > 0:
            target_speed = max(target_speed, self.min_speed)
        else:
            target_speed = 0  # Turn off fans if no load

        # Limit to 0-100% range
        self.fan_speed = max(0, min(100, target_speed))

    def _calculate_active_cells(self) -> int:
        """Calculate number of active cells based on load."""
        if self.current_load == 0:
            return 0

        # Determine how many cells to run based on load
        load_ratio = self.current_load / self.capacity
        active_cells = math.ceil(load_ratio * self.num_cells)

        # Ensure at least one cell is active if there's any load
        return max(1, min(active_cells, self.num_cells))

    def get_process_variables(self) -> Dict[str, Any]:
        """Return a dictionary of all process variables for the cooling tower."""
        approach = self.calculate_approach()
        range_temp = self.calculate_range()
        efficiency = self.calculate_efficiency()
        power = self.calculate_power_consumption()
        water_consumption = self.calculate_water_consumption()
        active_cells = self._calculate_active_cells()

        return {
            "name": self.name,
            "capacity": self.capacity,
            "current_load": self.current_load,
            "load_ratio": self.current_load / self.capacity if self.capacity > 0 else 0,
            "design_approach": self.design_approach,
            "current_approach": approach,
            "design_range": self.design_range,
            "current_range": range_temp,
            "design_wet_bulb": self.design_wet_bulb,
            "current_wet_bulb": self.current_wet_bulb,
            "entering_water_temp": self.entering_water_temp,
            "leaving_water_temp": self.leaving_water_temp,
            "water_flow": self.water_flow,
            "design_flow": self.design_flow,
            "min_speed": self.min_speed,
            "fan_speed": self.fan_speed,
            "tower_type": self.tower_type,
            "fan_power_rating": self.fan_power,
            "current_fan_power": power,
            "num_cells": self.num_cells,
            "active_cells": active_cells,
            "efficiency": efficiency,
            "water_consumption_gph": water_consumption,
        }

    @classmethod
    def get_process_variables_metadata(cls) -> Dict[str, Dict[str, Any]]:
        """Return metadata for all process variables."""
        return {
            "name": {
                "type": str,
                "label": "Cooling Tower Name",
                "description": "Unique identifier for the cooling tower",
            },
            "capacity": {
                "type": float,
                "label": "Capacity",
                "description": "Nominal heat rejection capacity",
                "unit": "tons",
            },
            "current_load": {
                "type": float,
                "label": "Current Load",
                "description": "Current heat rejection load",
                "unit": "tons",
            },
            "load_ratio": {
                "type": float,
                "label": "Load Ratio",
                "description": "Current load as a fraction of capacity (0-1)",
                "unit": "fraction",
            },
            "design_approach": {
                "type": float,
                "label": "Design Approach",
                "description": "Design approach temperature (LWT - WB)",
                "unit": "°F",
            },
            "current_approach": {
                "type": float,
                "label": "Current Approach",
                "description": "Current approach temperature (LWT - WB)",
                "unit": "°F",
            },
            "design_range": {
                "type": float,
                "label": "Design Range",
                "description": "Design range temperature (EWT - LWT)",
                "unit": "°F",
            },
            "current_range": {
                "type": float,
                "label": "Current Range",
                "description": "Current range temperature (EWT - LWT)",
                "unit": "°F",
            },
            "design_wet_bulb": {
                "type": float,
                "label": "Design Wet Bulb",
                "description": "Design ambient wet bulb temperature",
                "unit": "°F",
            },
            "current_wet_bulb": {
                "type": float,
                "label": "Current Wet Bulb",
                "description": "Current ambient wet bulb temperature",
                "unit": "°F",
            },
            "entering_water_temp": {
                "type": float,
                "label": "Entering Water Temperature",
                "description": "Temperature of water entering the cooling tower",
                "unit": "°F",
            },
            "leaving_water_temp": {
                "type": float,
                "label": "Leaving Water Temperature",
                "description": "Temperature of water leaving the cooling tower",
                "unit": "°F",
            },
            "water_flow": {
                "type": float,
                "label": "Water Flow",
                "description": "Current condenser water flow rate",
                "unit": "GPM",
            },
            "design_flow": {
                "type": float,
                "label": "Design Flow",
                "description": "Design condenser water flow rate",
                "unit": "GPM",
            },
            "min_speed": {
                "type": float,
                "label": "Minimum Fan Speed",
                "description": "Minimum allowable fan speed",
                "unit": "%",
            },
            "fan_speed": {
                "type": float,
                "label": "Fan Speed",
                "description": "Current fan speed",
                "unit": "%",
            },
            "tower_type": {
                "type": str,
                "label": "Tower Type",
                "description": "Type of cooling tower (counterflow or crossflow)",
                "options": ["counterflow", "crossflow"],
            },
            "fan_power_rating": {
                "type": float,
                "label": "Fan Power Rating",
                "description": "Rated fan power at 100% speed",
                "unit": "kW",
            },
            "current_fan_power": {
                "type": float,
                "label": "Current Fan Power",
                "description": "Current fan power consumption",
                "unit": "kW",
            },
            "num_cells": {
                "type": int,
                "label": "Number of Cells",
                "description": "Total number of cells in the cooling tower",
            },
            "active_cells": {
                "type": int,
                "label": "Active Cells",
                "description": "Number of currently active cells",
            },
            "efficiency": {
                "type": float,
                "label": "Efficiency",
                "description": "Current cooling tower thermal efficiency (0-1)",
                "unit": "fraction",
            },
            "water_consumption_gph": {
                "type": float,
                "label": "Water Consumption",
                "description": "Rate of water consumption due to evaporation, drift, and blowdown",
                "unit": "GPH",
            },
        }

    def __str__(self) -> str:
        """Return string representation of cooling tower state."""
        return (
            f"Cooling Tower {self.name}: "
            f"Load={self.current_load:.1f} tons ({self.current_load/self.capacity*100:.1f}%), "
            f"EWT={self.entering_water_temp:.1f}°F, "
            f"LWT={self.leaving_water_temp:.1f}°F, "
            f"WB={self.current_wet_bulb:.1f}°F, "
            f"Approach={self.calculate_approach():.1f}°F, "
            f"Range={self.calculate_range():.1f}°F, "
            f"Fan={self.fan_speed:.1f}%"
        )

    def get_condenser_water_supply_temp(self) -> float:
        """Calculate condenser water supply temperature (leaving water temperature)."""
        # This is the leaving water temperature
        return self.leaving_water_temp
