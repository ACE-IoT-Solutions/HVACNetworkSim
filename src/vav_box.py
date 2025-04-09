import math
import json

from bacpypes3.app import Application
from bacpypes3.object import AnalogValueObject, BinaryValueObject, MultiStateValueObject, CharacterStringValueObject


class PIDController:
    """Enhanced PID controller implementation with anti-windup and improved performance."""

    def __init__(self, kp=1.0, ki=0.1, kd=0.05, output_min=0.0, output_max=1.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_min = output_min
        self.output_max = output_max
        self.setpoint = 0
        self.previous_error = 0
        self.previous_value = 0
        self.integral = 0
        self.last_output = 0
        self.integral_windup_guard = 10.0  # Limit for integral term
        self.deadband = 0.5  # Small deadband to prevent micro-adjustments
        
        # Moving average for derivative calculation to reduce noise
        self.error_history = [0] * 3
        self.history_index = 0

    def compute(self, process_variable, setpoint=None):
        """Compute PID output based on process variable and setpoint."""
        if setpoint is not None:
            self.setpoint = setpoint
        
        # Avoid responding to tiny temperature changes
        if abs(process_variable - self.previous_value) < 0.1:
            # Temperature hasn't changed significantly, maintain previous output
            return self.last_output
        
        self.previous_value = process_variable

        # Calculate error with deadband to prevent micro-adjustments near setpoint
        raw_error = 0
        if process_variable > self.setpoint:  # Cooling mode
            if process_variable > self.setpoint + self.deadband:
                raw_error = process_variable - self.setpoint
        else:  # Heating mode
            if process_variable < self.setpoint - self.deadband:
                raw_error = self.setpoint - process_variable
        
        # Store error in history buffer for smoothed derivative
        self.error_history[self.history_index] = raw_error
        self.history_index = (self.history_index + 1) % len(self.error_history)
        
        # Use error sign to determine if we're heating or cooling
        error_sign = 1 if process_variable > self.setpoint else -1
        
        # Calculate error for proportional term
        error = raw_error * error_sign
        
        # Calculate P term
        p_term = self.kp * error

        # Calculate I term with anti-windup protection
        # Only integrate error if we're not saturated or if the integral will help move away from saturation
        if (self.last_output < self.output_max and error > 0) or (self.last_output > self.output_min and error < 0):
            self.integral += error
            
        # Implement integral windup guard
        self.integral = max(-self.integral_windup_guard, min(self.integral_windup_guard, self.integral))
        
        i_term = self.ki * self.integral

        # Calculate D term using moving average for smoother response
        avg_error = sum(self.error_history) / len(self.error_history)
        # Only apply derivative term if it will help stabilize (reduce oscillation)
        if abs(avg_error) < abs(self.previous_error):
            d_term = self.kd * (avg_error - self.previous_error)
        else:
            d_term = 0
        
        self.previous_error = error

        # Calculate output
        output = p_term + i_term + d_term

        # Clamp output to limits
        output = max(self.output_min, min(self.output_max, output))
        
        # Store output for next time
        self.last_output = output

        return output

    def reset(self):
        """Reset controller state."""
        self.previous_error = 0
        self.previous_value = 0
        self.integral = 0
        self.last_output = 0
        self.error_history = [0] * len(self.error_history)
        self.history_index = 0


class VAVBox:
    """Single zone VAV box model with reheat capability."""

    def __init__(self, name, min_airflow, max_airflow, zone_temp_setpoint,
                 deadband, discharge_air_temp_setpoint, has_reheat,
                 zone_area=400, zone_volume=3200, window_area=0,
                 window_orientation="north", thermal_mass=1.0):
        """Initialize VAV box with specified parameters.

        Args:
            name: Name/identifier for the VAV box
            min_airflow: Minimum airflow in CFM
            max_airflow: Maximum airflow in CFM
            zone_temp_setpoint: Zone temperature setpoint in °F
            deadband: Temperature deadband in °F
            discharge_air_temp_setpoint: Desired discharge air temperature in °F
            has_reheat: Boolean indicating if VAV box has reheat capability
            zone_area: Floor area of the zone in square feet
            zone_volume: Volume of the zone in cubic feet
            window_area: Window area in square feet
            window_orientation: Orientation of windows (north, south, east, west)
            thermal_mass: Thermal mass factor (1.0 = standard, higher = more mass)
        """
        # Configuration parameters
        self.name = name
        self.min_airflow = min_airflow
        self.max_airflow = max_airflow
        self.zone_temp_setpoint = zone_temp_setpoint
        self.deadband = deadband
        self.discharge_air_temp_setpoint = discharge_air_temp_setpoint
        self.has_reheat = has_reheat

        # Zone physical characteristics
        self.zone_area = zone_area
        self.zone_volume = zone_volume
        self.window_area = window_area
        self.window_orientation = window_orientation.lower()
        self.thermal_mass = thermal_mass

        # Current state
        self.current_airflow = min_airflow
        self.damper_position = 0  # 0 to 1 (closed to open)
        self.reheat_valve_position = 0  # 0 to 1 (closed to open)
        self.zone_temp = zone_temp_setpoint
        self.supply_air_temp = discharge_air_temp_setpoint
        self.mode = "deadband"  # "cooling", "heating", or "deadband"
        self.occupancy = 0  # Number of people in the zone

        # Controllers
        self.cooling_pid = PIDController(
            kp=0.5, ki=0.1, kd=0.05, output_min=0.0, output_max=1.0)
        self.heating_pid = PIDController(
            kp=0.5, ki=0.1, kd=0.05, output_min=0.0, output_max=1.0)

        # Energy tracking
        self.cooling_energy = 0
        self.heating_energy = 0

    def update(self, zone_temp, supply_air_temp):
        """Update VAV box state based on current conditions.

        Args:
            zone_temp: Current zone temperature in °F
            supply_air_temp: Current supply air temperature in °F
        """
        self.zone_temp = zone_temp
        self.supply_air_temp = supply_air_temp

        # Determine operating mode based on zone temperature relative to setpoint
        cooling_setpoint = self.zone_temp_setpoint + (self.deadband / 2)
        heating_setpoint = self.zone_temp_setpoint - (self.deadband / 2)

        if zone_temp > cooling_setpoint:
            self.mode = "cooling"
        elif zone_temp < heating_setpoint:
            self.mode = "heating"
        else:
            self.mode = "deadband"

        # Update control outputs based on mode
        if self.mode == "cooling":
            # In cooling mode, modulate damper position based on cooling demand
            # Use PID controller with zone temp and cooling setpoint
            cooling_demand = self.cooling_pid.compute(
                zone_temp, cooling_setpoint)

            # Map PID output to airflow scale - ensure we're above minimum
            self.damper_position = max(
                cooling_demand, self.min_airflow / self.max_airflow)
            self.current_airflow = self.min_airflow + \
                cooling_demand * (self.max_airflow - self.min_airflow)

            # No reheat in cooling mode
            self.reheat_valve_position = 0

        elif self.mode == "heating" and self.has_reheat:
            # In heating mode, maintain minimum airflow and modulate reheat valve
            self.current_airflow = self.min_airflow
            self.damper_position = self.min_airflow / self.max_airflow

            # Use PID controller for reheat valve position
            # For heating, we want more valve opening as temperature drops below heating setpoint
            heating_demand = self.heating_pid.compute(
                zone_temp, heating_setpoint)
            self.reheat_valve_position = heating_demand

        else:  # deadband or heating without reheat
            # Maintain minimum airflow with no reheat
            self.current_airflow = self.min_airflow
            self.damper_position = self.min_airflow / self.max_airflow
            self.reheat_valve_position = 0

        # Calculate energy usage for this update
        self._calculate_internal_energy()

    def get_discharge_air_temp(self):
        """Calculate and return the discharge air temperature after reheat."""
        if not self.has_reheat or self.reheat_valve_position == 0:
            return self.supply_air_temp

        # Simple model: reheat can raise temperature by up to 40°F above supply air temp
        max_reheat_delta_t = 40
        discharge_temp = self.supply_air_temp + \
            (self.reheat_valve_position * max_reheat_delta_t)

        return discharge_temp

    def _calculate_internal_energy(self):
        """Calculate and accumulate energy usage based on current operation."""
        # Constants for energy calculations
        AIR_DENSITY = 0.075  # lb/ft³
        SPECIFIC_HEAT = 0.24  # BTU/lb·°F

        # Calculate air mass flow (lb/hr)
        mass_flow = self.current_airflow * 60 * AIR_DENSITY  # CFM → ft³/hr → lb/hr

        # Calculate cooling energy (BTU/hr)
        if self.mode == "cooling":
            # Q = m * Cp * ΔT
            # In cooling, we're removing heat from the zone
            delta_t = self.zone_temp - self.supply_air_temp
            self.cooling_energy = mass_flow * SPECIFIC_HEAT * delta_t
        else:
            self.cooling_energy = 0

        # Calculate heating energy (BTU/hr)
        if self.mode == "heating" and self.has_reheat:
            # Q = m * Cp * ΔT
            # In heating, we're adding heat via reheat coil
            delta_t = self.get_discharge_air_temp() - self.supply_air_temp
            self.heating_energy = mass_flow * SPECIFIC_HEAT * \
                delta_t * self.reheat_valve_position
        else:
            self.heating_energy = 0

    def calculate_energy_usage(self):
        """Return current energy usage rates."""
        return {
            "cooling": self.cooling_energy,
            "heating": self.heating_energy,
            "total": abs(self.cooling_energy) + self.heating_energy
        }

    def set_occupancy(self, people_count):
        """Set the current occupancy level in the zone.

        Args:
            people_count: Number of people in the zone
        """
        self.occupancy = max(0, people_count)

    def calculate_occupancy_heat_gain(self):
        """Calculate heat gain from occupants in BTU/hr.

        Each person generates approximately: 
        - 250 BTU/hr sensible heat
        - 200 BTU/hr latent heat

        Returns:
            Total heat gain in BTU/hr
        """
        # Sensible heat directly affects air temperature
        sensible_heat_per_person = 250  # BTU/hr
        return self.occupancy * sensible_heat_per_person

    def calculate_solar_gain(self, time_of_day):
        """Calculate solar heat gain based on time of day and window orientation.

        Args:
            time_of_day: Tuple of (hour, minute) in 24-hour format

        Returns:
            Solar heat gain in BTU/hr
        """
        hour, minute = time_of_day
        decimal_hour = hour + minute / 60

        # No windows means no solar gain
        if self.window_area <= 0:
            return 0

        # Nighttime has minimal solar gain
        if hour < 6 or hour > 18:
            return 0.05 * self.window_area  # Minimal nighttime radiation

        # Define peak solar factors for each orientation
        # BTU/hr/ft² at peak sun exposure
        peak_solar_factors = {
            "north": 70,    # Least direct sun
            "east": 230,    # Morning sun
            "south": 200,   # Midday sun (northern hemisphere)
            "west": 230     # Afternoon sun
        }

        # Define peak hours for each orientation
        peak_hours = {
            "north": 12,    # Noon (minimal direct sun all day)
            "east": 9,      # 9 AM
            "south": 12,    # Noon
            "west": 15      # 3 PM
        }

        orientation = self.window_orientation
        if orientation not in peak_solar_factors:
            orientation = "north"  # Default to north for unknown orientations

        peak_solar = peak_solar_factors[orientation]
        peak_hour = peak_hours[orientation]

        # Calculate solar factor based on time difference from peak
        hours_from_peak = abs(decimal_hour - peak_hour)

        # Solar intensity drops off as we move away from peak hours
        # Using a sine wave approximation centered at peak hour
        if hours_from_peak > 6:
            factor = 0.05  # Minimal outside of daylight hours
        else:
            # Creates a nice curve with 1.0 at peak hour, tapering to 0.05 at ±6 hours
            factor = 0.05 + 0.95 * math.cos(math.pi * hours_from_peak / 6)

        return factor * peak_solar * self.window_area

    def calculate_thermal_behavior(self, minutes, outdoor_temp, vav_cooling_effect, time_of_day):
        """Calculate change in zone temperature over time based on thermal model.

        Args:
            minutes: Duration in minutes to simulate
            outdoor_temp: Outdoor air temperature in °F
            vav_cooling_effect: Factor representing VAV cooling (0-1)
            time_of_day: Tuple of (hour, minute)

        Returns:
            Temperature change in °F over the specified period
        """
        # Constants for thermal calculations
        AIR_DENSITY = 0.075  # lb/ft³
        AIR_SPECIFIC_HEAT = 0.24  # BTU/lb·°F

        # Calculate heat gains/losses

        # 1. Heat transfer through building envelope
        # Simplified U-value approach: BTU/hr/ft²/°F × area × temp difference
        average_u_value = 0.08  # Average U-value for walls, roof, etc. (improved insulation)
        # Approximate envelope area (walls + ceiling)
        envelope_area = 2 * math.sqrt(self.zone_area) * 8 + self.zone_area
        # Temperature difference driving heat transfer
        temp_diff_envelope = outdoor_temp - self.zone_temp
        # Add non-linearity to model better insulation at temperature extremes
        if abs(temp_diff_envelope) > 30:
            # Diminishing returns on heat transfer at extreme temperature differences
            temp_diff_envelope = 30 * (1 + math.log10(abs(temp_diff_envelope) / 30)) * (1 if temp_diff_envelope > 0 else -1)
        
        envelope_transfer = average_u_value * envelope_area * temp_diff_envelope

        # 2. Solar heat gain - with improved modeling for time of day
        solar_gain = self.calculate_solar_gain(time_of_day)

        # 3. Internal heat gains from people
        occupancy_gain = self.calculate_occupancy_heat_gain()

        # 4. Equipment and lighting (simplified assumption)
        equipment_gain = 1.5 * self.zone_area  # 1.5 BTU/hr/ft²

        # 5. VAV cooling/heating effect
        air_mass = AIR_DENSITY * self.zone_volume  # lb
        air_heat_capacity = air_mass * AIR_SPECIFIC_HEAT  # BTU/°F

        # Maximum cooling/heating rate from VAV in BTU/hr
        discharge_temp = self.get_discharge_air_temp()
        temp_diff = discharge_temp - self.zone_temp  # Positive if discharge is warmer, negative if cooler
        
        # Calculate efficiency factor that decreases as temperature differential increases
        # This represents diminishing returns at extreme temperature differences
        efficiency = 1.0
        if abs(temp_diff) > 15:
            efficiency = 1.0 - (abs(temp_diff) - 15) / 30  # Efficiency drops as temp diff increases
            efficiency = max(0.5, efficiency)  # Minimum 50% efficiency
            
        # VAV effect is based on airflow, temperature difference, and efficiency
        max_vav_rate = self.current_airflow * 60 * AIR_DENSITY * AIR_SPECIFIC_HEAT * abs(temp_diff) * efficiency
        
        # Determine if we're cooling or heating - use the sign of vav_cooling_effect to determine direction
        if vav_cooling_effect < 0:
            # Heating effect (positive value means adding heat)
            vav_effect = max_vav_rate * abs(vav_cooling_effect)
        else:
            # Cooling effect (negative value means removing heat)
            vav_effect = -max_vav_rate * vav_cooling_effect
            
        # Add baseline heating and cooling effects that represent natural equilibrium conditions
        # This ensures the zone doesn't get unrealistically hot or cold
        
        # Baseline heating (from building systems, internal gains, etc.)
        if self.zone_temp < self.zone_temp_setpoint - 2:
            # Scale heating based on how far below setpoint we are - more aggressive when colder
            temp_diff_from_setpoint = self.zone_temp_setpoint - self.zone_temp
            # Non-linear response - proportional to square of temperature difference
            baseline_heating = 500 * (temp_diff_from_setpoint ** 2) / 4
            # Cap the heating boost
            baseline_heating = min(5000, baseline_heating)
            vav_effect += baseline_heating
            
        # Baseline cooling (radiation to environment, natural convection, etc.)
        if self.zone_temp > self.zone_temp_setpoint + 2:
            # Scale cooling based on how far above setpoint we are - more aggressive when hotter
            temp_diff_from_setpoint = self.zone_temp - self.zone_temp_setpoint
            # Non-linear response - proportional to square of temperature difference
            baseline_cooling = -400 * (temp_diff_from_setpoint ** 2) / 4
            # Cap the cooling boost
            baseline_cooling = max(-4000, baseline_cooling)
            vav_effect += baseline_cooling

        # Sum all heat gains/losses (BTU/hr)
        net_heat_rate = envelope_transfer + solar_gain + occupancy_gain + equipment_gain + vav_effect

        # Apply thermal mass effects with improved modeling
        # Higher thermal mass leads to slower temperature changes
        # Add non-linearity to better model thermal inertia
        hours = minutes / 60
        
        # Scale the temperature change rate based on deviation from setpoint
        # This creates a natural tendency for temperatures to move toward the setpoint range
        setpoint_deviation = abs(self.zone_temp - self.zone_temp_setpoint)
        thermal_mass_factor = self.thermal_mass * (1 + 0.2 * setpoint_deviation)
        
        # Calculate temperature change with the enhanced thermal mass model
        temperature_change = (net_heat_rate * hours) / (air_heat_capacity * thermal_mass_factor)
        
        # Add damping for stability - limit maximum temperature change in a single interval
        max_change_per_hour = 5.0 / self.thermal_mass  # Maximum °F change per hour, adjusted for thermal mass
        max_change = max_change_per_hour * hours
        temperature_change = max(min(temperature_change, max_change), -max_change)

        return temperature_change

    def simulate_thermal_behavior(self, hours, interval_minutes, start_hour,
                                  outdoor_temps, occupied_hours, occupancy,
                                  supply_air_temp):
        """Simulate zone temperature over time with VAV control.

        Args:
            hours: Total simulation duration in hours
            interval_minutes: Simulation interval in minutes
            start_hour: Starting hour of day (0-23)
            outdoor_temps: Dict mapping hour (0-23) to outdoor temperature
            occupied_hours: List of tuples (start_hour, end_hour) for occupancy
            occupancy: Number of people during occupied hours
            supply_air_temp: Supply air temperature from AHU

        Returns:
            Dict containing simulation results
        """
        # Initialize results
        results = {
            'times': [],
            'zone_temps': [],
            'vav_airflows': [],
            'vav_modes': [],
            'discharge_temps': [],
            'solar_gains': [],
            'occupancy': []
        }

        # Calculate number of intervals
        intervals = int(hours * 60 / interval_minutes)

        # Simulation loop
        current_zone_temp = self.zone_temp

        for interval in range(intervals):
            # Calculate current time
            elapsed_minutes = interval * interval_minutes
            elapsed_hours = elapsed_minutes / 60

            current_hour = (start_hour + int(elapsed_hours)) % 24
            current_minute = int(elapsed_minutes % 60)
            time_of_day = (current_hour, current_minute)

            # Check if currently occupied
            is_occupied = False
            for start, end in occupied_hours:
                if start <= current_hour < end:
                    is_occupied = True
                    break

            # Set occupancy based on schedule
            current_occupancy = occupancy if is_occupied else 0
            self.set_occupancy(current_occupancy)

            # Get outdoor temperature (interpolate if needed)
            outdoor_temp = outdoor_temps.get(current_hour, 70)

            # Update VAV based on current zone temperature
            self.update(current_zone_temp, supply_air_temp)

            # Calculate VAV cooling effect
            cooling_effect = 0
            if self.mode == "cooling":
                cooling_effect = self.current_airflow / self.max_airflow
            elif self.mode == "heating" and self.has_reheat:
                cooling_effect = -self.reheat_valve_position

            # Calculate solar gain
            solar_gain = self.calculate_solar_gain(time_of_day)

            # Calculate temperature change
            temp_change = self.calculate_thermal_behavior(
                minutes=interval_minutes,
                outdoor_temp=outdoor_temp,
                vav_cooling_effect=cooling_effect,
                time_of_day=time_of_day
            )

            # Update zone temperature
            current_zone_temp += temp_change

            # Store results
            results['times'].append(time_of_day)
            results['zone_temps'].append(current_zone_temp)
            results['vav_airflows'].append(self.current_airflow)
            results['vav_modes'].append(self.mode)
            results['discharge_temps'].append(self.get_discharge_air_temp())
            results['solar_gains'].append(solar_gain)
            results['occupancy'].append(current_occupancy)

        return results

    def get_process_variables(self):
        """Return a dictionary of all process variables for the VAV box."""
        discharge_temp = self.get_discharge_air_temp()
        energy = self.calculate_energy_usage()

        return {
            "name": self.name,
            "zone_temp": self.zone_temp,
            "supply_air_temp": self.supply_air_temp,
            "discharge_air_temp": discharge_temp,
            # Alias for consistency with other equipment
            "current_airflow": self.current_airflow,
            "damper_position": self.damper_position,
            "reheat_valve_position": self.reheat_valve_position,
            "mode": self.mode,
            "occupancy": self.occupancy,
            "zone_temp_setpoint": self.zone_temp_setpoint,
            "deadband": self.deadband,
            "discharge_air_temp_setpoint": self.discharge_air_temp_setpoint,
            "min_airflow": self.min_airflow,
            "max_airflow": self.max_airflow,
            "has_reheat": self.has_reheat,
            "zone_area": self.zone_area,
            "zone_volume": self.zone_volume,
            "window_area": self.window_area,
            "window_orientation": self.window_orientation,
            "thermal_mass": self.thermal_mass,
            "cooling_energy": energy["cooling"],
            "heating_energy": energy["heating"],
            "total_energy": energy["total"]
        }

    @classmethod
    def get_process_variables_metadata(cls):
        """Return metadata for all process variables."""
        return {
             "zone_temp": {
                "type": float,
                "label": "Zone Temperature",
                "description": "Current zone temperature in °F",
                "unit": "°F"
            },
            "supply_air_temp": {
                "type": float,
                "label": "Supply Air Temperature",
                "description": "Supply air temperature from AHU in °F",
                "unit": "°F"
            },
            "discharge_air_temp": {
                "type": float,
                "label": "Discharge Air Temperature",
                "description": "Air temperature after any reheat in °F",
                "unit": "°F"
            },
            "leaving_water_temp": {
                "type": float,
                "label": "Leaving Water Temperature",
                "description": "Alias for discharge air temperature for consistency with other equipment",
                "unit": "°F"
            },
            "current_airflow": {
                "type": float,
                "label": "Current Airflow",
                "description": "Current airflow through the VAV box",
                "unit": "CFM"
            },
            "damper_position": {
                "type": float,
                "label": "Damper Position",
                "description": "Current damper position as a fraction (0-1)",
                "unit": "fraction"
            },
            "reheat_valve_position": {
                "type": float,
                "label": "Reheat Valve Position",
                "description": "Current reheat valve position as a fraction (0-1)",
                "unit": "fraction"
            },
            "mode": {
                "type": str,
                "label": "Operating Mode",
                "description": "Current operating mode (cooling, heating, or deadband)",
                "options": ["cooling", "heating", "deadband"]
            },
            "occupancy": {
                "type": int,
                "label": "Occupancy Count",
                "description": "Number of people occupying the zone"
            },
            "zone_temp_setpoint": {
                "type": float,
                "label": "Zone Temperature Setpoint",
                "description": "Target zone temperature in °F",
                "unit": "°F"
            },
            "deadband": {
                "type": float,
                "label": "Temperature Deadband",
                "description": "Temperature range around setpoint where neither heating nor cooling is active",
                "unit": "°F"
            },
            "discharge_air_temp_setpoint": {
                "type": float,
                "label": "Discharge Air Temperature Setpoint",
                "description": "Target discharge air temperature in °F",
                "unit": "°F"
            },
            "min_airflow": {
                "type": float,
                "label": "Minimum Airflow",
                "description": "Minimum allowable airflow through the VAV box",
                "unit": "CFM"
            },
            "max_airflow": {
                "type": float,
                "label": "Maximum Airflow",
                "description": "Maximum allowable airflow through the VAV box",
                "unit": "CFM"
            },
            "has_reheat": {
                "type": bool,
                "label": "Has Reheat",
                "description": "Whether the VAV box has reheat capability"
            },
            "zone_area": {
                "type": float,
                "label": "Zone Area",
                "description": "Floor area of the zone",
                "unit": "sq ft"
            },
            "zone_volume": {
                "type": float,
                "label": "Zone Volume",
                "description": "Volume of the zone",
                "unit": "cu ft"
            },
            "window_area": {
                "type": float,
                "label": "Window Area",
                "description": "Total window area in the zone",
                "unit": "sq ft"
            },
            "window_orientation": {
                "type": str,
                "label": "Window Orientation",
                "description": "Primary orientation of windows (north, south, east, west)",
                "options": ["north", "south", "east", "west"]
            },
            "thermal_mass": {
                "type": float,
                "label": "Thermal Mass Factor",
                "description": "Factor representing zone's thermal mass (higher means more mass)"
            },
            "cooling_energy": {
                "type": float,
                "label": "Cooling Energy",
                "description": "Current cooling energy usage",
                "unit": "BTU/hr"
            },
            "heating_energy": {
                "type": float,
                "label": "Heating Energy",
                "description": "Current heating energy usage",
                "unit": "BTU/hr"
            },
            "total_energy": {
                "type": float,
                "label": "Total Energy",
                "description": "Total energy usage",
                "unit": "BTU/hr"
            }
        }

    def __str__(self):
        """Return string representation of VAV box state."""
        return (f"VAV Box {self.name}: "
                f"Mode={self.mode}, "
                f"Zone Temp={self.zone_temp:.1f}°F, "
                f"Airflow={self.current_airflow:.0f} CFM, "
                f"Damper={self.damper_position*100:.0f}%, "
                f"Reheat={self.reheat_valve_position*100:.0f}%, "
                f"Occupancy={self.occupancy}")

    def create_bacpypes3_device(self, device_id=None, device_name=None,
                                network_interface_name="vlan", mac_address="0x01", virtual_network=None):
        """
        Create a BACpypes3 device representation of this VAV box.

        Args:
            device_id: BACnet device ID (defaults to a hash of the VAV name)
            device_name: BACnet device name (defaults to VAV name)
            network_interface_name: Name of the virtual network to connect to
            mac_address: MAC address for this device on the virtual network

        Returns:
            BACpypes3 Application object
        """

        # Create JSON-compatible configuration list for the application
        # Following the pattern from ip-to-vlan.json
        app_config = [
            # Device Object
            {
                "apdu-segment-timeout": 1000,
                "apdu-timeout": 3000,
                "application-software-version": "1.0",
                "database-revision": 1,
                "firmware-revision": "N/A",
                "max-apdu-length-accepted": 1024,
                "model-name": "N/A",
                "number-of-apdu-retries": 3,
                "object-identifier": f"device,{device_id}",
                "object-name": device_name,
                "object-type": "device",
                "protocol-revision": 22,
                "protocol-version": 1,
                "segmentation-supported": "segmented-both",
                "system-status": "operational",
                "vendor-identifier": 999,
                "vendor-name": "ACEHVACNetwork",
                "description": f"Virtual VAV Box - {self.name}"
            },
            # Network Port
            {
                "changes-pending": False,
                "mac-address": mac_address,
                "network-interface-name": network_interface_name,
                "network-type": "virtual",
                "object-identifier": "network-port,1",
                "object-name": "NetworkPort-1",
                "object-type": "network-port",
                "out-of-service": False,
                "protocol-level": "bacnet-application",
                "reliability": "no-fault-detected"
            },
        ]

        # Create the application using from_json method (which is synchronous)
        app = Application.from_json(app_config)

        # Add data points to the application config
        point_id = 3  # Start at ID 3 since 1 and 2 are used by device and network-port

        # Get current values
        process_vars = self.get_process_variables()
        metadata = self.get_process_variables_metadata()

        # Create and add objects for each variable
        for point_name, point_meta in metadata.items():
            # Skip complex types
            if point_meta["type"] not in (float, int, bool, str):
                continue

            # Get current value
            value = process_vars.get(point_name)
            if value is None:
                continue

            # Create appropriate object config based on type
            if point_meta["type"] in (float, int):
                # Get units
                units = "no-units"
                if "unit" in point_meta:
                    # Direct unit conversion
                    unit_text = point_meta["unit"]
                    if unit_text in ("°F", "degF"):
                        units = "degrees-fahrenheit"
                    elif unit_text in ("CFM", "ft³/min"):
                        units = "cubic-feet-per-minute"
                    elif unit_text == "fraction":
                        units = "percent"
                    elif unit_text == "sq ft":
                        units = "square-feet"
                    elif unit_text == "cu ft":
                        units = "cubic-feet"

                # Create analog value object

                point_obj = AnalogValueObject(objectIdentifier=f"analog-value,{point_id}",
                                              objectName=point_name,
                                              description=point_meta["label"],
                                              presentValue=float(value),
                                              units=units
                                              )
                app.add_object(point_obj)

            elif point_meta["type"] == bool:
                # Create binary value object
                point_obj = BinaryValueObject(objectIdentifier=f"binary-value,{point_id}",
                                              objectName=point_name,
                                              description=point_meta["label"],
                                              presentValue=bool(value)
                                              )
            elif point_meta["type"] == str:
                point_obj = MultiStateValueObject(objectIdentifier=f"multi-state-value,{point_id}",
                                                  objectName=point_name,
                                                  description=point_meta["label"],
                                                  presentValue=point_meta["options"].index(
                                                      value) + 1,
                                                  numberOfStates=len(
                                                      point_meta["options"]),
                                                  stateText=point_meta["options"]
                                                  )
            else:
                point_obj = CharacterStringValueObject(objectIdentifier=f"character-string-value,{point_id}",
                                                       objectName=point_name,
                                                       description=point_meta["label"],
                                                       presentValue=str(value)
                                                       )
                app.add_object(point_obj)
            point_id += 1

        # Store a reference to the VAV box in the app for updates
        app.vav_box = self

        # In BACpypes3, the Application is already running when created
        # No explicit startup() call needed

        # Return the application
        return app

    async def update_bacpypes3_device(self, app):
        """
        Update a BACpypes3 device with current VAV box state.

        Args:
            app: BACpypes3 Application object created by create_bacpypes3_device
        """
        # Get current process variables
        process_vars = self.get_process_variables()
        metadata = self.get_process_variables_metadata()

        # Keep track of updated points
        updated_points = 0

        # For each object in the application
        for obj in app.objectIdentifier.values():
            # Skip if not a point object with objectName
            if not hasattr(obj, "objectName"):
                continue

            point_name = obj.objectName

            # Skip if this is not one of our process variables
            if point_name not in process_vars:
                continue

            value = process_vars[point_name]

            # Skip complex types
            if isinstance(value, (dict, list, tuple)) or value is None:
                continue

            try:
                # Handle different object types appropriately
                if hasattr(obj, "objectType"):
                    obj_type = obj.objectType

                    # For multi-state values, convert string to index
                    if obj_type == "multi-state-value" and point_name in metadata:
                        if "options" in metadata[point_name]:
                            options = metadata[point_name]["options"]
                            if value in options:
                                # 1-based index for BACnet MSV
                                idx = options.index(value) + 1
                                obj.presentValue = idx
                                updated_points += 1
                                continue

                    # For analog values, ensure float
                    elif obj_type == "analog-value" and (isinstance(value, (int, float))):
                        obj.presentValue = float(value)
                        updated_points += 1
                        continue

                    # For binary values, ensure boolean
                    elif obj_type == "binary-value":
                        obj.presentValue = bool(value)
                        updated_points += 1
                        continue

                    # For our string properties represented as analog values
                    # We'll just update the length as a proxy for the actual string
                    # In a real implementation, we'd need a better way to handle strings
                    elif obj_type == "analog-value" and obj.description and "string length" in obj.description:
                        obj.presentValue = float(len(str(value)))
                        updated_points += 1
                        continue

                # Fallback to direct assignment if specific handling not applied
                obj.presentValue = value
                updated_points += 1

            except Exception as e:
                print(f"Error updating {point_name}: {e}")

        # Print update summary
        if updated_points > 0:
            print(f"Updated {updated_points} BACnet points for {self.name}")
