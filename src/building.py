import math
from datetime import datetime, timedelta
from collections import defaultdict

class Building:
    """
    Building class that serves as a container for all HVAC equipment and 
    manages building-wide data such as outdoor conditions and solar position.
    """
    
    def __init__(self, name, location, latitude, longitude, floor_area, 
                 num_floors, orientation=0, year_built=None, timezone=None):
        """
        Initialize Building with specified parameters.
        
        Args:
            name: Name of the building
            location: Geographic location (city, state/country)
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            floor_area: Total floor area in square feet
            num_floors: Number of floors
            orientation: Building orientation in degrees from North (0-359)
            year_built: Year the building was constructed
            timezone: Timezone string (e.g., "America/New_York")
        """
        # Building characteristics
        self.name = name
        self.location = location
        self.latitude = latitude
        self.longitude = longitude
        self.floor_area = floor_area
        self.num_floors = num_floors
        self.orientation = orientation
        self.year_built = year_built
        self.timezone = timezone
        
        # HVAC equipment
        self.air_handling_units = {}  # Dictionary of AHUs by name
        self.zones = {}  # Dictionary of VAV zones by name
        
        # Outdoor conditions (default values)
        self.outdoor_temp = 70  # °F
        self.outdoor_humidity = 50  # %
        self.wind_speed = 0  # mph
        self.wind_direction = 0  # degrees
        self.solar_ghi = 0  # W/m²
        self.solar_dni = 0  # W/m²
        self.solar_dhi = 0  # W/m²
        self.cloud_cover = 0  # %
        
        # Simulation time
        self.simulation_time = None
        
        # Simulation results
        self.simulation_results = []
    
    @property
    def ahu_names(self):
        """Get list of AHU names in the building."""
        return list(self.air_handling_units.keys())
    
    @property
    def zone_names(self):
        """Get list of zone names in the building."""
        return list(self.zones.keys())
    
    def add_air_handling_unit(self, ahu):
        """Add an Air Handling Unit to the building."""
        self.air_handling_units[ahu.name] = ahu
    
    def add_zone(self, vav_box):
        """Add a VAV box zone to the building."""
        self.zones[vav_box.name] = vav_box
    
    def set_outdoor_conditions(self, temperature=None, humidity=None, 
                              wind_speed=None, wind_direction=None,
                              solar_ghi=None, solar_dni=None, solar_dhi=None,
                              cloud_cover=None):
        """Set outdoor weather conditions."""
        if temperature is not None:
            self.outdoor_temp = temperature
        if humidity is not None:
            self.outdoor_humidity = humidity
        if wind_speed is not None:
            self.wind_speed = wind_speed
        if wind_direction is not None:
            self.wind_direction = wind_direction
        if solar_ghi is not None:
            self.solar_ghi = solar_ghi
        if solar_dni is not None:
            self.solar_dni = solar_dni
        if solar_dhi is not None:
            self.solar_dhi = solar_dhi
        if cloud_cover is not None:
            self.cloud_cover = cloud_cover
    
    def set_time(self, datetime_obj):
        """Set the simulation time."""
        self.simulation_time = datetime_obj
    
    def get_time_of_day(self):
        """Get current simulation time as (hour, minute) tuple."""
        if self.simulation_time is None:
            return (0, 0)
        return (self.simulation_time.hour, self.simulation_time.minute)
    
    def get_day_of_year(self):
        """Get day of year from current simulation time."""
        if self.simulation_time is None:
            return 1
        return self.simulation_time.timetuple().tm_yday
    
    def set_zone_temperatures(self, zone_temps):
        """
        Set zone temperatures for simulation.
        
        Args:
            zone_temps: Dictionary mapping zone names to temperatures
        """
        for zone_name, temp in zone_temps.items():
            if zone_name in self.zones:
                # Store the temperature but don't update the VAV yet
                # This will be done in update_equipment()
                self.zones[zone_name].zone_temp = temp
    
    def update_equipment(self):
        """Update all HVAC equipment with current conditions."""
        # First update all air handling units
        for ahu in self.air_handling_units.values():
            # Gather zone temperatures for all zones connected to this AHU
            zone_temps = {}
            for vav in ahu.vav_boxes:
                zone_temps[vav.name] = vav.zone_temp
            
            # Update the AHU with current outdoor temperature
            ahu.update(zone_temps, self.outdoor_temp)
    
    def calculate_solar_position(self):
        """
        Calculate solar position (altitude and azimuth) based on current time and location.
        
        Returns:
            Dictionary with solar altitude and azimuth in degrees
        """
        if self.simulation_time is None:
            return {"altitude": 0, "azimuth": 0}
        
        # Get day of year and time as decimal hours
        day_of_year = self.get_day_of_year()
        hour, minute = self.get_time_of_day()
        decimal_hour = hour + minute / 60
        
        # Solar declination
        declination = 23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365))
        
        # Solar hour angle
        lst = decimal_hour + 4 * self.longitude / 60  # Local solar time
        solar_hour_angle = 15 * (lst - 12)  # 15 degrees per hour
        
        # Convert latitude and declination to radians
        lat_rad = math.radians(self.latitude)
        decl_rad = math.radians(declination)
        hour_rad = math.radians(solar_hour_angle)
        
        # Solar altitude
        sin_altitude = (math.sin(lat_rad) * math.sin(decl_rad) + 
                        math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_rad))
        altitude = math.degrees(math.asin(sin_altitude))
        
        # Solar azimuth
        cos_azimuth = ((math.sin(decl_rad) - math.sin(lat_rad) * sin_altitude) / 
                       (math.cos(lat_rad) * math.cos(math.asin(sin_altitude))))
        
        # Avoid domain errors
        if cos_azimuth > 1:
            cos_azimuth = 1
        elif cos_azimuth < -1:
            cos_azimuth = -1
            
        azimuth = math.degrees(math.acos(cos_azimuth))
        
        # Adjust azimuth based on time of day
        if decimal_hour > 12:
            azimuth = 360 - azimuth
        
        return {"altitude": altitude, "azimuth": azimuth}
    
    def calculate_total_energy(self):
        """
        Calculate total energy usage for the building.
        
        Returns:
            Dictionary with energy totals by type (cooling, heating, fan, total)
        """
        # Initialize energy counters
        total_cooling = 0
        total_heating = 0
        total_fan = 0
        
        # Sum up energy from all air handling units
        for ahu in self.air_handling_units.values():
            energy = ahu.calculate_energy_usage()
            total_cooling += energy["cooling"]
            total_heating += energy["heating"]
            total_fan += energy["fan"]
        
        return {
            "cooling": total_cooling,
            "heating": total_heating,
            "fan": total_fan,
            "total": total_cooling + total_heating + total_fan
        }
    
    def run_simulation_step(self, minutes=15):
        """
        Run a single simulation step.
        
        Args:
            minutes: Length of simulation step in minutes
            
        Returns:
            Dictionary with simulation results
        """
        if self.simulation_time is None:
            self.simulation_time = datetime.now()
        
        # Calculate solar position based on time and location
        solar_position = self.calculate_solar_position()
        
        # Update all equipment with current conditions
        self.update_equipment()
        
        # For each zone, calculate thermal behavior
        for zone in self.zones.values():
            # Find the AHU serving this zone
            for ahu in self.air_handling_units.values():
                if zone in ahu.vav_boxes:
                    # Calculate cooling/heating effect
                    if zone.mode == "cooling":
                        vav_effect = zone.current_airflow / zone.max_airflow
                    elif zone.mode == "heating" and zone.has_reheat:
                        vav_effect = -zone.reheat_valve_position
                    else:
                        vav_effect = 0
                    
                    # Calculate zone temperature change
                    temp_change = zone.calculate_thermal_behavior(
                        minutes=minutes,
                        outdoor_temp=self.outdoor_temp,
                        vav_cooling_effect=vav_effect,
                        time_of_day=self.get_time_of_day()
                    )
                    
                    # Update zone temperature
                    zone.zone_temp += temp_change
                    break
        
        # Calculate energy usage
        energy = self.calculate_total_energy()
        
        # Store current state
        result = {
            "time": self.simulation_time,
            "outdoor_temp": self.outdoor_temp,
            "outdoor_humidity": self.outdoor_humidity,
            "solar_position": solar_position,
            "solar_ghi": self.solar_ghi,
            "zone_temps": {name: zone.zone_temp for name, zone in self.zones.items()},
            "energy": energy
        }
        
        # Advance simulation time
        self.simulation_time += timedelta(minutes=minutes)
        
        return result
    
    def run_simulation(self, weather_data, interval_minutes=15, initial_zone_temps=None):
        """
        Run a simulation for multiple time steps using provided weather data.
        
        Args:
            weather_data: List of dictionaries with time, temperature, and other weather data
            interval_minutes: Simulation interval in minutes
            initial_zone_temps: Dictionary of initial zone temperatures
            
        Returns:
            List of dictionaries with simulation results
        """
        results = []
        
        # Set initial zone temperatures if provided
        if initial_zone_temps:
            self.set_zone_temperatures(initial_zone_temps)
        
        # Run simulation for each weather data point
        for data in weather_data:
            # Set simulation time
            self.set_time(data["time"])
            
            # Set outdoor conditions from weather data
            outdoor_params = {}
            for key in ["temperature", "humidity", "wind_speed", "wind_direction", 
                        "solar_ghi", "solar_dni", "solar_dhi", "cloud_cover"]:
                if key in data:
                    outdoor_params[key] = data[key]
            
            self.set_outdoor_conditions(**outdoor_params)
            
            # Run simulation step
            result = self.run_simulation_step(interval_minutes)
            results.append(result)
        
        return results
    
    def generate_energy_report(self, simulation_results):
        """
        Generate an energy report from simulation results.
        
        Args:
            simulation_results: List of dictionaries with simulation results
            
        Returns:
            Dictionary with energy report data
        """
        if not simulation_results:
            return {
                "total_energy": 0,
                "energy_by_type": {"cooling": 0, "heating": 0, "fan": 0},
                "energy_by_equipment": {},
                "peak_demand": 0
            }
        
        # Calculate total energy usage
        total_cooling = 0
        total_heating = 0
        total_fan = 0
        peak_demand = 0
        
        # Energy usage by equipment
        equipment_energy = defaultdict(float)
        
        # Process each time step
        for result in simulation_results:
            # Sum energy usage
            energy = result["energy"]
            total_cooling += energy["cooling"]
            total_heating += energy["heating"]
            total_fan += energy["fan"]
            
            # Track peak demand
            peak_demand = max(peak_demand, energy["total"])
            
            # Calculate energy by equipment
            for ahu_name, ahu in self.air_handling_units.items():
                ahu_energy = ahu.calculate_energy_usage()
                equipment_energy[ahu_name] += ahu_energy["cooling"] + ahu_energy["heating"] + ahu_energy["fan"]
        
        # Create the energy report
        report = {
            "total_energy": total_cooling + total_heating + total_fan,
            "energy_by_type": {
                "cooling": total_cooling,
                "heating": total_heating,
                "fan": total_fan
            },
            "energy_by_equipment": dict(equipment_energy),
            "peak_demand": peak_demand
        }
        
        return report
    
    def get_process_variables(self):
        """Return a dictionary of all process variables for the building."""
        energy = self.calculate_total_energy()
        solar_position = self.calculate_solar_position()
        
        variables = {
            "name": self.name,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "floor_area": self.floor_area,
            "num_floors": self.num_floors,
            "orientation": self.orientation,
            "year_built": self.year_built,
            "timezone": self.timezone,
            "outdoor_temp": self.outdoor_temp,
            "outdoor_humidity": self.outdoor_humidity,
            "wind_speed": self.wind_speed,
            "wind_direction": self.wind_direction,
            "solar_ghi": self.solar_ghi,
            "solar_dni": self.solar_dni,
            "solar_dhi": self.solar_dhi,
            "cloud_cover": self.cloud_cover,
            "simulation_time": self.simulation_time,
            "time_of_day": self.get_time_of_day(),
            "day_of_year": self.get_day_of_year(),
            "solar_altitude": solar_position["altitude"],
            "solar_azimuth": solar_position["azimuth"],
            "equipment_count": {
                "ahu": len(self.air_handling_units),
                "zones": len(self.zones)
            },
            "ahu_names": self.ahu_names,
            "zone_names": self.zone_names,
            "energy": energy
        }
        
        # Add zone temperature information
        zone_temps = {}
        for name, zone in self.zones.items():
            zone_temps[name] = zone.zone_temp
        variables["zone_temps"] = zone_temps
        
        return variables
    
    @classmethod
    def get_process_variables_metadata(cls):
        """Return metadata for all process variables."""
        return {
            "name": {
                "type": str,
                "label": "Building Name",
                "description": "Name of the building"
            },
            "location": {
                "type": str,
                "label": "Location",
                "description": "Geographic location (city, state/country)"
            },
            "latitude": {
                "type": float,
                "label": "Latitude",
                "description": "Latitude in decimal degrees",
                "unit": "degrees"
            },
            "longitude": {
                "type": float,
                "label": "Longitude",
                "description": "Longitude in decimal degrees",
                "unit": "degrees"
            },
            "floor_area": {
                "type": float,
                "label": "Floor Area",
                "description": "Total floor area of the building",
                "unit": "sq ft"
            },
            "num_floors": {
                "type": int,
                "label": "Number of Floors",
                "description": "Number of floors in the building"
            },
            "orientation": {
                "type": float,
                "label": "Orientation",
                "description": "Building orientation in degrees from North",
                "unit": "degrees"
            },
            "year_built": {
                "type": int,
                "label": "Year Built",
                "description": "Year the building was constructed"
            },
            "timezone": {
                "type": str,
                "label": "Timezone",
                "description": "Timezone string (e.g., 'America/New_York')"
            },
            "outdoor_temp": {
                "type": float,
                "label": "Outdoor Temperature",
                "description": "Current outdoor air temperature",
                "unit": "°F"
            },
            "outdoor_humidity": {
                "type": float,
                "label": "Outdoor Humidity",
                "description": "Current outdoor relative humidity",
                "unit": "%"
            },
            "wind_speed": {
                "type": float,
                "label": "Wind Speed",
                "description": "Current wind speed",
                "unit": "mph"
            },
            "wind_direction": {
                "type": float,
                "label": "Wind Direction",
                "description": "Current wind direction in degrees",
                "unit": "degrees"
            },
            "solar_ghi": {
                "type": float,
                "label": "Solar GHI",
                "description": "Global Horizontal Irradiance",
                "unit": "W/m²"
            },
            "solar_dni": {
                "type": float,
                "label": "Solar DNI",
                "description": "Direct Normal Irradiance",
                "unit": "W/m²"
            },
            "solar_dhi": {
                "type": float,
                "label": "Solar DHI",
                "description": "Diffuse Horizontal Irradiance",
                "unit": "W/m²"
            },
            "cloud_cover": {
                "type": float,
                "label": "Cloud Cover",
                "description": "Current cloud cover",
                "unit": "%"
            },
            "simulation_time": {
                "type": "datetime",
                "label": "Simulation Time",
                "description": "Current time in the simulation"
            },
            "time_of_day": {
                "type": tuple,
                "label": "Time of Day",
                "description": "Current time as (hour, minute) tuple"
            },
            "day_of_year": {
                "type": int,
                "label": "Day of Year",
                "description": "Current day of year (1-366)"
            },
            "solar_altitude": {
                "type": float,
                "label": "Solar Altitude",
                "description": "Sun's altitude above horizon",
                "unit": "degrees"
            },
            "solar_azimuth": {
                "type": float,
                "label": "Solar Azimuth",
                "description": "Sun's azimuth angle",
                "unit": "degrees"
            },
            "equipment_count": {
                "type": dict,
                "label": "Equipment Count",
                "description": "Count of different equipment types in the building"
            },
            "ahu_names": {
                "type": list,
                "label": "AHU Names",
                "description": "Names of all AHUs in the building"
            },
            "zone_names": {
                "type": list,
                "label": "Zone Names",
                "description": "Names of all zones in the building"
            },
            "zone_temps": {
                "type": dict,
                "label": "Zone Temperatures",
                "description": "Current temperature of each zone",
                "unit": "°F"
            },
            "energy": {
                "type": dict,
                "label": "Energy Usage",
                "description": "Current energy usage by type"
            }
        }
    
    def __str__(self):
        """Return string representation of the building."""
        return (f"Building: {self.name}\n"
                f"Location: {self.location} ({self.latitude}, {self.longitude})\n"
                f"Floor Area: {self.floor_area} sq ft, Floors: {self.num_floors}\n"
                f"Equipment: {len(self.air_handling_units)} AHUs, {len(self.zones)} Zones\n"
                f"Current Outdoor Conditions: {self.outdoor_temp}°F, {self.outdoor_humidity}% RH")