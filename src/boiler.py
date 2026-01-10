import logging
from typing import Any, Dict, Optional

from .base_equip import BACPypesApplicationMixin
from src.core.constants import (
    WATER_HEAT_CONSTANT,
    BTU_PER_KWH,
    NATURAL_GAS_BTU_PER_CF,
    CONDENSING_THRESHOLD_TEMP,
)

logger = logging.getLogger(__name__)


class Boiler(BACPypesApplicationMixin):
    """
    Boiler class that models the performance of gas-fired or electric boilers.
    """

    def __init__(
        self,
        name: str,
        fuel_type: str,
        capacity: float,
        design_efficiency: float,
        design_entering_water_temp: float,
        design_leaving_water_temp: float,
        min_part_load_ratio: float,
        design_hot_water_flow: float,
        condensing: bool = False,
        turndown_ratio: float = 4.0,
    ) -> None:
        """
        Initialize Boiler with specified parameters.

        Args:
            name: Name of the boiler
            fuel_type: Type of fuel ("gas" or "electric")
            capacity: Nominal heating capacity in MBH (thousand BTU/hr)
            design_efficiency: Efficiency at design conditions (0-1)
            design_entering_water_temp: Design entering water temperature in °F
            design_leaving_water_temp: Design leaving water temperature in °F
            min_part_load_ratio: Minimum allowable part load ratio (0-1)
            design_hot_water_flow: Design hot water flow rate in GPM
            condensing: Whether the boiler is condensing type (for gas boilers)
            turndown_ratio: Turndown ratio (maximum capacity / minimum capacity)
        """
        # Design parameters
        self.name = name
        self.fuel_type = fuel_type.lower()
        self.capacity = capacity
        self.design_efficiency = design_efficiency
        self.design_entering_water_temp = design_entering_water_temp
        self.design_leaving_water_temp = design_leaving_water_temp
        self.min_part_load_ratio = min_part_load_ratio
        self.design_hot_water_flow = design_hot_water_flow
        self.condensing = condensing
        self.turndown_ratio = turndown_ratio

        # Current state
        self.current_load = 0  # Current heating load in MBH
        self.entering_water_temp = design_entering_water_temp  # Default EWT
        self.leaving_water_temp = design_leaving_water_temp  # Default LWT
        self.current_efficiency = 0  # Current efficiency (0 when off)
        self.hot_water_flow = 0  # Current hot water flow rate in GPM
        self.ambient_temp = 70  # Default ambient temperature in °F
        self.is_on = False  # Boiler on/off status

        # Cycling parameters
        self.min_on_time = 10  # Default minimum on time in minutes
        self.min_off_time = 5  # Default minimum off time in minutes
        self.cycles_per_hour_limit = 6  # Default maximum cycles per hour
        self.cycles_in_current_hour = 0  # Cycle counter
        self.time_in_current_state = 0  # Time in current on/off state

        # Energy tracking
        self.fuel_consumption = 0  # Units depend on fuel type

        # Validate parameters
        if fuel_type.lower() not in ["gas", "electric"]:
            raise ValueError("Fuel type must be 'gas' or 'electric'")

    def update_load(
        self,
        load: float,
        entering_water_temp: float,
        hot_water_flow: float,
        ambient_temp: float,
        simulation_time_step: Optional[float] = None,
    ) -> None:
        """
        Update boiler with new load and conditions.

        Args:
            load: Current heating load in MBH
            entering_water_temp: Entering water temperature in °F
            hot_water_flow: Hot water flow rate in GPM
            ambient_temp: Ambient temperature in °F
            simulation_time_step: Time step in minutes (for cycling logic)
        """
        # Handle cycling logic if time step is provided
        if simulation_time_step is not None:
            self._handle_cycling(load, simulation_time_step)
            if not self.is_on and load > 0:
                # Boiler wants to turn on but can't due to cycling constraints
                load = 0
        elif load > 0:
            # If no time step provided but load > 0, just turn on
            self.is_on = True
        elif load == 0:
            self.is_on = False

        # Apply capacity limits
        if load > self.capacity:
            limited_load = self.capacity
        elif load > 0 and load < self.capacity / self.turndown_ratio:
            # Don't go below minimum firing rate
            limited_load = self.capacity / self.turndown_ratio
        else:
            limited_load = load

        self.current_load = limited_load
        self.entering_water_temp = entering_water_temp
        self.hot_water_flow = hot_water_flow
        self.ambient_temp = ambient_temp

        # Calculate performance at these conditions
        if self.is_on:
            self._calculate_performance(limited_load)
        else:
            self.current_efficiency = 0
            self.leaving_water_temp = self.entering_water_temp  # No heat addition

    def set_leaving_water_temp_setpoint(self, setpoint: float) -> None:
        """Set leaving hot water temperature setpoint."""
        self.design_leaving_water_temp = setpoint

    def set_cycling_parameters(
        self, min_on_time: float = 10, min_off_time: float = 5, cycles_per_hour_limit: int = 6
    ) -> None:
        """Set boiler cycling control parameters."""
        self.min_on_time = min_on_time
        self.min_off_time = min_off_time
        self.cycles_per_hour_limit = cycles_per_hour_limit

    def calculate_fuel_consumption(self) -> Dict[str, float]:
        """
        Calculate fuel consumption based on load and efficiency.

        Returns a dictionary with appropriate units based on fuel type.
        """
        if self.current_load == 0 or not self.is_on:
            if self.fuel_type == "gas":
                return {"therms_per_hour": 0, "cubic_feet_per_hour": 0}
            else:  # electric
                return {"kilowatt_hours": 0}

        if self.fuel_type == "gas":
            # Gas consumption in therms per hour
            # 1 therm = 100,000 BTU, so MBH / 100 = therms/hr
            therms_per_hour = self.current_load / (self.current_efficiency * 100)

            # Convert to cubic feet of natural gas
            cubic_feet_per_hour = therms_per_hour * 100000 / NATURAL_GAS_BTU_PER_CF

            return {"therms_per_hour": therms_per_hour, "cubic_feet_per_hour": cubic_feet_per_hour}
        else:  # electric
            # Electric consumption in kWh
            # Convert MBH to kW: 1 kW = BTU_PER_KWH BTU/hr
            kilowatt_hours = self.current_load * 1000 / (self.current_efficiency * BTU_PER_KWH)

            return {"kilowatt_hours": kilowatt_hours}

    def calculate_energy_consumption(self, hours: float = 1) -> Dict[str, float]:
        """
        Calculate energy consumption for a specified duration.

        Returns a dictionary with appropriate units based on fuel type.
        """
        fuel_consumption = self.calculate_fuel_consumption()

        if self.fuel_type == "gas":
            # Convert hourly consumption to total consumption
            therms = fuel_consumption["therms_per_hour"] * hours
            cubic_feet = fuel_consumption["cubic_feet_per_hour"] * hours

            # Also calculate MMBTU for consistent comparison
            mmbtu = therms / 10  # 1 therm = 0.1 MMBTU

            return {"therms": therms, "cubic_feet": cubic_feet, "mmbtu": mmbtu}
        else:  # electric
            # Calculate kWh consumption
            kwh = fuel_consumption["kilowatt_hours"] * hours

            # Also calculate MMBTU for consistent comparison
            mmbtu = kwh * 3412 / 1000000  # 1 kWh = 3412 BTU

            return {"kwh": kwh, "mmbtu": mmbtu}

    def _calculate_performance(self, load: float) -> None:
        """Calculate performance at current conditions."""
        # Calculate leaving hot water temperature based on load and flow
        if self.hot_water_flow > 0:
            delta_t = (load * 1000) / (WATER_HEAT_CONSTANT * self.hot_water_flow)

            # If load exceeds capacity, may not reach setpoint
            target_lwt = self.entering_water_temp + delta_t

            # If target exceeds setpoint, we're at setpoint
            self.leaving_water_temp = max(self.design_leaving_water_temp, target_lwt)
        else:
            # No flow - can't transfer heat
            self.leaving_water_temp = self.entering_water_temp

        # Calculate efficiency at these conditions
        self.current_efficiency = self._calculate_efficiency(load)

    def _calculate_efficiency(self, load: float) -> float:
        """Calculate efficiency at current conditions."""
        if load <= 0 or not self.is_on:
            return 0

        # Start with design efficiency
        efficiency = self.design_efficiency

        # Adjust for part load ratio
        plr = load / self.capacity

        if self.fuel_type == "gas":
            # Gas boiler efficiency varies with load
            # Typical part-load curve (polynomial approximation)
            if plr <= 0.3:
                plr_factor = 0.95 + 0.05 * (plr / 0.3)
            elif plr <= 0.5:
                plr_factor = 1.0
            else:
                plr_factor = 1.0 - 0.05 * ((plr - 0.5) / 0.5)

            # Adjust for return water temperature (for condensing boilers)
            if self.condensing:
                # Condensing boilers have higher efficiency with lower return temps
                # Below condensing threshold return temp allows condensing
                if self.entering_water_temp < CONDENSING_THRESHOLD_TEMP:
                    # Bonus efficiency for condensing operation
                    condensing_bonus = (
                        0.1 * (CONDENSING_THRESHOLD_TEMP - self.entering_water_temp) / 30
                    )
                    condensing_factor = 1.0 + min(0.15, condensing_bonus)  # Cap at 15% bonus
                else:
                    condensing_factor = 1.0
            else:
                condensing_factor = 1.0

            # Minor adjustment for ambient temperature - jacket losses
            ambient_factor = 1.0 - 0.005 * max(0, 70 - self.ambient_temp) / 20

            # Apply all factors
            efficiency *= plr_factor * condensing_factor * ambient_factor

        else:  # electric
            # Electric boilers have nearly constant efficiency regardless of load
            # Minimal variations due to controls and jacket losses
            ambient_factor = 1.0 - 0.001 * max(0, 70 - self.ambient_temp) / 20
            efficiency *= ambient_factor

        # Ensure efficiency is in reasonable range
        return max(0.5, min(0.99, efficiency))

    def _handle_cycling(self, requested_load: float, time_step: float) -> None:
        """Handle boiler cycling logic."""
        # Update time in current state
        self.time_in_current_state += time_step

        if self.is_on:
            # Currently on - check if we need to turn off
            if requested_load <= 0:
                # Want to turn off, but check minimum on time
                if self.time_in_current_state >= self.min_on_time:
                    # Can turn off
                    self.is_on = False
                    self.time_in_current_state = 0
                    self.cycles_in_current_hour += 1
            # Else stay on
        else:
            # Currently off - check if we need to turn on
            if requested_load > 0:
                # Want to turn on, but check minimum off time and cycle limit
                if (
                    self.time_in_current_state >= self.min_off_time
                    and self.cycles_in_current_hour < self.cycles_per_hour_limit
                ):
                    # Can turn on
                    self.is_on = True
                    self.time_in_current_state = 0
                    self.cycles_in_current_hour += 1  # Count as a cycle when turning on
            # Else stay off

        # Reset cycle counter every hour
        if time_step > 0:
            self.cycles_in_current_hour = max(
                0, self.cycles_in_current_hour - (time_step / 60) * self.cycles_per_hour_limit
            )

    def get_process_variables(self) -> Dict[str, Any]:
        """Return a dictionary of all process variables for the boiler."""
        fuel_consumption = self.calculate_fuel_consumption()

        variables = {
            "name": self.name,
            "fuel_type": self.fuel_type,
            "capacity": self.capacity,
            "current_load": self.current_load,
            "load_ratio": self.current_load / self.capacity if self.capacity > 0 else 0,
            "design_efficiency": self.design_efficiency,
            "current_efficiency": self.current_efficiency,
            "entering_water_temp": self.entering_water_temp,
            "leaving_water_temp": self.leaving_water_temp,
            "hot_water_flow": self.hot_water_flow,
            "design_hot_water_flow": self.design_hot_water_flow,
            "min_part_load_ratio": self.min_part_load_ratio,
            "turndown_ratio": self.turndown_ratio,
            "condensing": self.condensing,
            "is_on": self.is_on,
            "ambient_temp": self.ambient_temp,
            "design_entering_water_temp": self.design_entering_water_temp,
            "design_leaving_water_temp": self.design_leaving_water_temp,
        }

        # Add cycling-related variables
        variables.update(
            {
                "min_on_time": self.min_on_time,
                "min_off_time": self.min_off_time,
                "cycles_per_hour_limit": self.cycles_per_hour_limit,
                "cycles_in_current_hour": self.cycles_in_current_hour,
                "time_in_current_state": self.time_in_current_state,
            }
        )

        # Add fuel-specific variables
        if self.fuel_type == "gas":
            variables.update(
                {
                    "therms_per_hour": fuel_consumption.get("therms_per_hour", 0),
                    "cubic_feet_per_hour": fuel_consumption.get("cubic_feet_per_hour", 0),
                }
            )
        else:  # electric
            variables.update({"kilowatt_hours": fuel_consumption.get("kilowatt_hours", 0)})

        return variables

    @classmethod
    def get_process_variables_metadata(cls) -> Dict[str, Dict[str, Any]]:
        """Return metadata for all process variables."""
        return {
            "name": {
                "type": str,
                "label": "Boiler Name",
                "description": "Unique identifier for the boiler",
            },
            "fuel_type": {
                "type": str,
                "label": "Fuel Type",
                "description": "Type of fuel used by the boiler",
                "options": ["gas", "electric"],
            },
            "capacity": {
                "type": float,
                "label": "Heating Capacity",
                "description": "Nominal heating capacity",
                "unit": "MBH",
            },
            "current_load": {
                "type": float,
                "label": "Current Load",
                "description": "Current heating load",
                "unit": "MBH",
            },
            "load_ratio": {
                "type": float,
                "label": "Load Ratio",
                "description": "Current load as a fraction of capacity (0-1)",
                "unit": "fraction",
            },
            "design_efficiency": {
                "type": float,
                "label": "Design Efficiency",
                "description": "Efficiency at design conditions (0-1)",
                "unit": "fraction",
            },
            "current_efficiency": {
                "type": float,
                "label": "Current Efficiency",
                "description": "Current operating efficiency (0-1)",
                "unit": "fraction",
            },
            "entering_water_temp": {
                "type": float,
                "label": "Entering Water Temperature",
                "description": "Temperature of water entering the boiler (return)",
                "unit": "°F",
            },
            "leaving_water_temp": {
                "type": float,
                "label": "Leaving Water Temperature",
                "description": "Temperature of water leaving the boiler (supply)",
                "unit": "°F",
            },
            "hot_water_flow": {
                "type": float,
                "label": "Hot Water Flow",
                "description": "Current hot water flow rate",
                "unit": "GPM",
            },
            "design_hot_water_flow": {
                "type": float,
                "label": "Design Hot Water Flow",
                "description": "Design hot water flow rate",
                "unit": "GPM",
            },
            "min_part_load_ratio": {
                "type": float,
                "label": "Minimum Part Load Ratio",
                "description": "Lowest allowable operating point as fraction of capacity",
                "unit": "fraction",
            },
            "turndown_ratio": {
                "type": float,
                "label": "Turndown Ratio",
                "description": "Ratio of maximum to minimum firing rate",
            },
            "condensing": {
                "type": bool,
                "label": "Condensing",
                "description": "Whether the boiler is a condensing type (gas boilers only)",
            },
            "is_on": {
                "type": bool,
                "label": "Is On",
                "description": "Whether the boiler is currently running",
            },
            "ambient_temp": {
                "type": float,
                "label": "Ambient Temperature",
                "description": "Temperature of the boiler room",
                "unit": "°F",
            },
            "design_entering_water_temp": {
                "type": float,
                "label": "Design Entering Water Temperature",
                "description": "Design temperature for entering water",
                "unit": "°F",
            },
            "design_leaving_water_temp": {
                "type": float,
                "label": "Design Leaving Water Temperature",
                "description": "Design temperature for leaving water",
                "unit": "°F",
            },
            # Cycling parameters
            "min_on_time": {
                "type": float,
                "label": "Minimum On Time",
                "description": "Minimum time the boiler must remain on once started",
                "unit": "minutes",
            },
            "min_off_time": {
                "type": float,
                "label": "Minimum Off Time",
                "description": "Minimum time the boiler must remain off once stopped",
                "unit": "minutes",
            },
            "cycles_per_hour_limit": {
                "type": float,
                "label": "Cycles Per Hour Limit",
                "description": "Maximum allowed cycles per hour",
            },
            "cycles_in_current_hour": {
                "type": float,
                "label": "Cycles In Current Hour",
                "description": "Number of on/off cycles in the current hour",
            },
            "time_in_current_state": {
                "type": float,
                "label": "Time In Current State",
                "description": "Time spent in current on/off state",
                "unit": "minutes",
            },
            # Gas specific variables
            "therms_per_hour": {
                "type": float,
                "label": "Therms Per Hour",
                "description": "Gas consumption rate in therms per hour",
                "unit": "therms/hr",
            },
            "cubic_feet_per_hour": {
                "type": float,
                "label": "Cubic Feet Per Hour",
                "description": "Gas consumption rate in cubic feet per hour",
                "unit": "cf/hr",
            },
            # Electric specific variables
            "kilowatt_hours": {
                "type": float,
                "label": "Kilowatt Hours",
                "description": "Electricity consumption rate",
                "unit": "kW",
            },
        }

    def __str__(self) -> str:
        """Return string representation of boiler state."""
        status = "ON" if self.is_on else "OFF"

        return (
            f"Boiler {self.name} ({self.fuel_type.capitalize()}, {status}): "
            f"Load={self.current_load:.1f} MBH ({self.current_load/self.capacity*100:.1f}%), "
            f"EWT={self.entering_water_temp:.1f}°F, "
            f"LWT={self.leaving_water_temp:.1f}°F, "
            f"Efficiency={self.current_efficiency*100:.1f}%"
        )
