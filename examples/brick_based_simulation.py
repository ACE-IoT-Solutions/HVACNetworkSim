#!/usr/bin/env python3
"""
HVAC System simulation built from a BRICK schema definition.

This simulation demonstrates:
1. Parsing a BRICK schema file to extract building topology
2. Building a simulation model based on the extracted structure
3. Creating an HVAC simulation with BACnet integration using BACpypes3
4. Simulating system behavior with real-time visualization

The simulation uses the same core components as complete_bacpypes3_simulation_minute.py
but builds the system structure from a BRICK schema definition.
"""

import asyncio
import math
import random
import signal
import time
from collections import defaultdict
import re
from typing import List

try:
    from rdflib import Graph, Namespace, URIRef, Literal
    from rdflib.namespace import RDF, RDFS
    RDFLIB_AVAILABLE = True
except ImportError:
    print("rdflib not installed. Cannot parse BRICK schema.")
    RDFLIB_AVAILABLE = False

try:
    from bacpypes3.vlan import VirtualNetwork
    from bacpypes3.app import Application
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.local.networkport import NetworkPortObject
    from bacpypes3.local.analog import AnalogValueObject
    from bacpypes3.local.binary import BinaryValueObject
    from bacpypes3.local.multistate import MultiStateValueObject
    from bacpypes3.primitivedata import CharacterString, Real
    BACPYPES_AVAILABLE = True
except ImportError:
    print("BACpypes3 not installed. Running in simulation-only mode.")
    BACPYPES_AVAILABLE = False

from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.cooling_tower import CoolingTower
from src.chiller import Chiller
from src.boiler import Boiler
from src.building import Building

# Constants
IP_ADDRESS = "10.88.0.2"
IP_SUBNET_MASK = "255.255.0.0"

# Global references
all_devices: List[Application] = []
virtual_network = None
controller_app = None
exit_event = None
data_log = defaultdict(list)  # For storing simulation data
start_time = None


class BrickParser:
    """Parser for BRICK schema files to extract building structure."""
    
    def __init__(self, file_path):
        """
        Initialize the BRICK parser.
        
        Args:
            file_path: Path to the BRICK TTL file
        """
        if not RDFLIB_AVAILABLE:
            raise ImportError("rdflib is required to parse BRICK schema files")
        
        self.file_path = file_path
        self.graph = Graph()
        self.g = self.graph  # Alias for shorter access
        
        # Load the TTL file
        self.g.parse(file_path, format="turtle")
        
        # Define namespaces
        self.BRICK = Namespace("https://brickschema.org/schema/Brick#")
        self.REF = Namespace("https://brickschema.org/schema/Brick/ref#")
        
        # Try to extract the main namespace from the file
        self.main_ns = None
        for prefix, uri in self.g.namespaces():
            if prefix in ('ns1', 'ns2', 'ns3', 'ns4') or prefix == '':
                self.main_ns = Namespace(uri)
                break
        
        if not self.main_ns:
            # Fallback to a default namespace
            self.main_ns = Namespace("http://buildsys.org/ontologies/bldg1#")
        
        # Bind namespaces for queries
        self.g.bind("brick", self.BRICK)
        self.g.bind("ref", self.REF)
        self.g.bind("main", self.main_ns)
    
    def extract_building_info(self):
        """Extract basic building information."""
        building_info = {}
        
        # Find building instance
        for building in self.g.subjects(RDF.type, self.BRICK.Building):
            # Get building name
            for name in self.g.objects(building, RDFS.label):
                building_info["name"] = str(name)
                break
            
            # Get building area
            for area_node in self.g.objects(building, self.BRICK.area):
                for value in self.g.objects(area_node, self.BRICK.value):
                    # Extract numeric value from the string
                    match = re.search(r'(\d+)', str(value))
                    if match:
                        building_info["area"] = int(match.group(1))
                        break
            
            # Only process the first building found
            break
        
        return building_info
    
    def extract_ahu_info(self):
        """Extract AHU information and their relationships."""
        ahu_info = {}
        
        for ahu in self.g.subjects(RDF.type, self.BRICK.Air_Handler_Unit):
            ahu_id = str(ahu).split("#")[-1]
            
            # Initialize AHU entry
            ahu_info[ahu_id] = {
                "id": ahu_id,
                "feeds": [],
                "points": [],
                "fed_by": []
            }
            
            # Get VAV boxes fed by this AHU
            for vav in self.g.objects(ahu, self.BRICK.feeds):
                vav_id = str(vav).split("#")[-1]
                ahu_info[ahu_id]["feeds"].append(vav_id)
            
            # Get data points related to this AHU
            for point in self.g.objects(ahu, self.BRICK.hasPoint):
                point_id = str(point).split("#")[-1]
                ahu_info[ahu_id]["points"].append(point_id)
                
                # Get point type
                for point_type in self.g.objects(point, RDF.type):
                    if "Temperature" in str(point_type):
                        temp_type = str(point_type).split("#")[-1]
                        ahu_info[ahu_id][temp_type] = point_id
            
            # Get equipment feeding this AHU
            for source in self.g.objects(ahu, self.BRICK.isFedBy):
                source_id = str(source).split("#")[-1]
                ahu_info[ahu_id]["fed_by"].append(source_id)
        
        return ahu_info
    
    def extract_vav_info(self):
        """Extract VAV box information and their relationships."""
        vav_info = {}
        
        for vav in self.g.subjects(RDF.type, self.BRICK.VAV):
            vav_id = str(vav).split("#")[-1]
            
            # Initialize VAV entry
            vav_info[vav_id] = {
                "id": vav_id,
                "feeds": [],
                "points": [],
                "has_reheat": False
            }
            
            # Get zones fed by this VAV
            for zone in self.g.objects(vav, self.BRICK.feeds):
                zone_id = str(zone).split("#")[-1]
                vav_info[vav_id]["feeds"].append(zone_id)
            
            # Get data points related to this VAV
            for point in self.g.objects(vav, self.BRICK.hasPoint):
                point_id = str(point).split("#")[-1]
                point_label = None
                
                # Try to get point label
                for label in self.g.objects(point, RDFS.label):
                    point_label = str(label)
                    break
                
                # Get point type
                point_info = {"id": point_id, "label": point_label, "types": []}
                for point_type in self.g.objects(point, RDF.type):
                    type_name = str(point_type).split("#")[-1]
                    point_info["types"].append(type_name)
                    
                    # Check for reheat
                    if "Reheat" in type_name or "Valve" in type_name and "Heat" in type_name:
                        vav_info[vav_id]["has_reheat"] = True
                
                vav_info[vav_id]["points"].append(point_info)
                
                # Categorize specific point types for easier access
                if point_label:
                    lower_label = point_label.lower()
                    
                    if "zone air temp" in lower_label and "setpoint" not in lower_label:
                        vav_info[vav_id]["zone_temp_sensor"] = point_id
                    
                    elif "setpoint" in lower_label:
                        vav_info[vav_id]["temp_setpoint"] = point_id
                    
                    elif "damper" in lower_label:
                        vav_info[vav_id]["damper_command"] = point_id
                    
                    elif "reheat" in lower_label:
                        vav_info[vav_id]["reheat_command"] = point_id
                        vav_info[vav_id]["has_reheat"] = True
                    
                    elif "air flow" in lower_label:
                        vav_info[vav_id]["airflow_sensor"] = point_id
        
        return vav_info
    
    def extract_zone_info(self):
        """Extract zone information and their relationships."""
        zone_info = {}
        
        for zone in self.g.subjects(RDF.type, self.BRICK.HVAC_Zone):
            zone_id = str(zone).split("#")[-1]
            
            # Initialize zone entry
            zone_info[zone_id] = {
                "id": zone_id,
                "rooms": []
            }
            
            # Get rooms in this zone
            for room in self.g.objects(zone, self.BRICK.hasPart):
                room_id = str(room).split("#")[-1]
                zone_info[zone_id]["rooms"].append(room_id)
        
        return zone_info
    
    def extract_chiller_info(self):
        """Extract chiller information and their relationships."""
        chiller_info = {}
        
        for chiller in self.g.subjects(RDF.type, self.BRICK.Chiller):
            chiller_id = str(chiller).split("#")[-1]
            
            # Initialize chiller entry
            chiller_info[chiller_id] = {
                "id": chiller_id,
                "points": []
            }
            
            # Get data points related to this chiller
            for point in self.g.objects(chiller, self.BRICK.hasPoint):
                point_id = str(point).split("#")[-1]
                point_label = None
                
                # Try to get point label
                for label in self.g.objects(point, RDFS.label):
                    point_label = str(label)
                    break
                
                point_info = {"id": point_id, "label": point_label, "types": []}
                
                # Get point type
                for point_type in self.g.objects(point, RDF.type):
                    type_name = str(point_type).split("#")[-1]
                    point_info["types"].append(type_name)
                
                chiller_info[chiller_id]["points"].append(point_info)
                
                # Categorize specific point types for easier access
                if point_label:
                    lower_label = point_label.lower()
                    
                    if "supply temp" in lower_label:
                        chiller_info[chiller_id]["supply_temp_sensor"] = point_id
                    
                    elif "return temp" in lower_label:
                        chiller_info[chiller_id]["return_temp_sensor"] = point_id
        
        return chiller_info
    
    def extract_all_equipment(self):
        """Extract all equipment information from the BRICK schema."""
        building_info = self.extract_building_info()
        ahu_info = self.extract_ahu_info()
        vav_info = self.extract_vav_info()
        zone_info = self.extract_zone_info()
        chiller_info = self.extract_chiller_info()
        
        # Build the complete structure
        building_structure = {
            "building": building_info,
            "ahus": ahu_info,
            "vavs": vav_info,
            "zones": zone_info,
            "chillers": chiller_info
        }
        
        return building_structure


def generate_weather_data(season="winter", minute_resolution=True):
    """Generate synthetic weather data for a 24-hour period with minute resolution."""
    weather_data = {}
    
    # Adjust temperature range based on season
    if season == "winter":
        temp_min, temp_max = 30, 55  # Cold winter day
    elif season == "summer":
        temp_min, temp_max = 70, 95  # Hot summer day
    elif season == "spring":
        temp_min, temp_max = 50, 75  # Mild spring day
    elif season == "fall":
        temp_min, temp_max = 45, 70  # Mild fall day
    else:
        temp_min, temp_max = 50, 75  # Default
    
    temp_range = temp_max - temp_min
    
    if minute_resolution:
        # Generate data for each minute of the day (1440 minutes)
        for minute in range(1440):
            hour = minute // 60
            hour_fraction = minute / 60
            
            # Calculate hour in radians for sinusoidal pattern (lowest at 5am, highest at 3pm)
            hour_rad = math.pi * (hour_fraction - 5) / 12
            
            # Outdoor temperature model
            temp = temp_min + temp_range * math.sin(hour_rad)**2
            
            # Add small random fluctuations for more realistic data
            temp += random.uniform(-0.2, 0.2)
            
            # Humidity model (highest at night/morning, lowest in afternoon)
            humidity = 70 - 30 * math.sin(hour_rad)**2
            humidity += random.uniform(-1, 1)  # Small random fluctuations
            
            # Solar radiation (0 at night, peak at noon)
            if 7 <= hour <= 17:  # Daylight hours
                solar_factor = math.sin(math.pi * (hour_fraction - 7) / 10)
                if season == "summer":
                    max_solar = 800  # Summer solar radiation peak
                elif season == "winter":
                    max_solar = 500  # Winter solar radiation peak
                else:
                    max_solar = 650  # Spring/fall
                solar_ghi = max_solar * solar_factor
            else:
                solar_ghi = 0
                
            # Wind speed and direction with small variations
            wind_speed = 5 + 5 * math.sin(hour_fraction / 12 * math.pi)
            wind_speed += random.uniform(-0.5, 0.5)  # Add small variations
            wind_direction = (hour * 15 + random.randint(-5, 5)) % 360
            
            # Create weather data point
            weather_data[minute] = {
                "temperature": temp,
                "humidity": humidity,
                "solar_ghi": solar_ghi,
                "wind_speed": wind_speed,
                "wind_direction": wind_direction,
                "hour": hour,
                "minute": minute % 60
            }
    else:
        # Generate data for each hour (original behavior)
        for hour in range(24):
            # Outdoor temperature model (lowest at 5am, highest at 3pm)
            temp = temp_min + temp_range * math.sin(math.pi * (hour - 5) / 12)**2
            
            # Humidity model
            humidity = 70 - 30 * math.sin(math.pi * (hour - 5) / 12)**2
            
            # Solar radiation (0 at night, peak at noon)
            if 7 <= hour <= 17:  # Daylight hours
                solar_factor = math.sin(math.pi * (hour - 7) / 10)
                if season == "summer":
                    max_solar = 800
                elif season == "winter":
                    max_solar = 500
                else:
                    max_solar = 650
                solar_ghi = max_solar * solar_factor
            else:
                solar_ghi = 0
                
            # Wind speed and direction
            wind_speed = 5 + 5 * math.sin(hour / 12 * math.pi)
            wind_direction = (hour * 15) % 360
            
            # Create weather data point
            weather_data[hour] = {
                "temperature": temp,
                "humidity": humidity,
                "solar_ghi": solar_ghi,
                "wind_speed": wind_speed,
                "wind_direction": wind_direction,
                "hour": hour,
                "minute": 0
            }
        
    return weather_data


def estimate_wet_bulb(dry_bulb, relative_humidity):
    """Estimate wet bulb temperature from dry bulb and relative humidity."""
    # Simplified equation for wet bulb calculation
    wet_bulb = dry_bulb * math.atan(0.151977 * math.sqrt(relative_humidity + 8.313659)) + \
               math.atan(dry_bulb + relative_humidity) - math.atan(relative_humidity - 1.676331) + \
               0.00391838 * (relative_humidity)**(3/2) * math.atan(0.023101 * relative_humidity) - 4.686035
    
    # Ensure wet bulb is less than or equal to dry bulb
    return min(wet_bulb, dry_bulb)


async def create_building_controller(network_name, device_id=1000, mac_address="0x01"):
    """Create a controller device that can interact with the HVAC equipment."""
    if not BACPYPES_AVAILABLE:
        return None
        
    # Create configuration for the controller
    controller_config = [
        # Device Object
        {
            "apdu-segment-timeout": 1000,
            "apdu-timeout": 3000,
            "object-identifier": f"device,{device_id}",
            "object-name": "Building Automation Controller",
            "object-type": "device",
            "vendor-identifier": 999,
            "vendor-name": "HVACNetwork",
            "model-name": "BMS Controller",
            "protocol-version": 1,
            "protocol-revision": 22,
            "application-software-version": "1.0",
            "description": "Central Building Management System Controller"
        },
        # IP Network Port
        {
            "bacnet-ip-mode": "normal",
            "bacnet-ip-udp-port": 47808,
            "changes-pending": False,
            "ip-address": IP_ADDRESS,
            "ip-subnet-mask": IP_SUBNET_MASK,
            "link-speed": 0.0,
            "mac-address": f"{IP_ADDRESS}:47808",
            "network-number": 100,
            "network-number-quality": "configured",
            "network-type": "ipv4",
            "object-identifier": "network-port,1",
            "object-name": "NetworkPort-1",
            "object-type": "network-port",
            "out-of-service": False,
            "protocol-level": "bacnet-application",
            "reliability": "no-fault-detected"
        },
        # Virtual Network Port
        {
            "changes-pending": False,
            "mac-address": mac_address,
            "network-interface-name": network_name,
            "network-number": 200,
            "network-type": "virtual",
            "object-identifier": "network-port,2",
            "object-name": "NetworkPort-2",
            "object-type": "network-port",
            "out-of-service": False,
            "protocol-level": "bacnet-application",
            "reliability": "no-fault-detected"
        }
    ]
    
    try:
        # Create the controller
        controller = Application.from_json(controller_config)
        print(f"Created BMS controller device (ID: {device_id}) on network: {network_name}")
        return controller
    except Exception as e:
        print(f"Error creating controller: {e}")
        return None


async def simulate_vav_box(vav, app, weather_data, minutes_per_second=1, start_time=(6, 0)):
    """Maintain an ongoing simulation of a VAV box, updating every minute."""
    current_hour, current_minute = start_time
    current_minute_of_day = current_hour * 60 + current_minute
    previous_time = (current_hour, current_minute)
    
    # Constant AHU supply air temperature
    supply_air_temp = 55  # °F
    
    # Calculate sleep time for simulation speed
    sleep_time = 1 / minutes_per_second  # seconds per simulated minute
    
    # Office occupied from 8 AM to 6 PM
    occupied_hours = [(8, 18)]
    
    print(f"\nStarting simulation for VAV box {vav.name}...")
    print(f"Speed: {minutes_per_second}x (1 minute per {sleep_time:.1f} seconds)")
    
    try:
        while not exit_event.is_set():
            # Get current simulation time
            current_minute_of_day = current_minute_of_day % 1440  # Wrap around at end of day
            hour = current_minute_of_day // 60
            minute = current_minute_of_day % 60
            
            # Get weather for current minute
            weather = weather_data[current_minute_of_day]
            outdoor_temp = weather["temperature"]
            
            # Add some random variation to make it more realistic
            outdoor_temp += random.uniform(-0.2, 0.2)  # Small variation
            
            # Check if occupied based on time of day
            is_occupied = any(start <= hour < end for start, end in occupied_hours)
            
            # Set occupancy - higher during peak hours
            if is_occupied:
                # Peak occupancy hours 9-11am and 1-3pm
                if (9 <= hour < 11) or (13 <= hour < 15):
                    occupancy_count = 10
                else:
                    occupancy_count = 5
            else:
                occupancy_count = 0
                
            # Set occupancy
            vav.set_occupancy(occupancy_count)
            
            # Only reset if temperature is truly unrealistic
            if vav.zone_temp < 20 or vav.zone_temp > 120:
                print(f"Resetting unrealistic temperature: {vav.zone_temp:.1f}°F to setpoint")
                vav.zone_temp = vav.zone_temp_setpoint
                
            # Update VAV box with current conditions
            vav.update(vav.zone_temp, supply_air_temp)
            
            # Simulate thermal behavior for the time elapsed since last update
            vav_effect = 0
            if vav.mode == "cooling":
                vav_effect = vav.damper_position  # Positive effect for cooling
            elif vav.mode == "heating" and vav.has_reheat:
                vav_effect = -vav.reheat_valve_position  # Negative effect for heating
                
            # Calculate minutes elapsed since last update
            prev_hour, prev_minute = previous_time
            prev_minute_of_day = prev_hour * 60 + prev_minute
            minutes_elapsed = (current_minute_of_day - prev_minute_of_day) % 1440
            if minutes_elapsed <= 0:
                minutes_elapsed = 1  # Ensure at least 1 minute of simulation
                
            # Cap the maximum simulation step to avoid large temperature jumps
            minutes_elapsed = min(minutes_elapsed, 10)
                
            temp_change = vav.calculate_thermal_behavior(
                minutes=minutes_elapsed,
                outdoor_temp=outdoor_temp,
                vav_cooling_effect=vav_effect,
                time_of_day=(hour, minute)
            )
            
            # Our thermal model now handles rate-of-change limits internally
            # This is now redundant, but we'll keep a more generous limit as a safety check
            max_allowed_change = 1.0  # Maximum 1°F change per minute to prevent simulation errors
            temp_change = max(min(temp_change, max_allowed_change), -max_allowed_change)
            
            # Update zone temperature with calculated change
            vav.zone_temp += temp_change
            
            # Save current time for next update
            previous_time = (hour, minute)
            
            # Update the BACnet device
            if app:
                await vav.update_bacnet_device()
            
            # Log data for later analysis
            data_log["time"].append(f"{hour:02d}:{minute:02d}")
            data_log[f"{vav.name}_temp"].append(vav.zone_temp)
            data_log[f"{vav.name}_mode"].append(vav.mode)
            data_log[f"{vav.name}_airflow"].append(vav.current_airflow)
            data_log["outdoor_temp"].append(outdoor_temp)
            
            # Display current simulation time and key values
            # Only print updates every 5 minutes to reduce console output
            if minute % 5 == 0:
                time_str = f"{hour:02d}:{minute:02d}"
                print(f"{vav.name} - Time: {time_str}, Outdoor: {outdoor_temp:.1f}°F, " + 
                      f"Zone: {vav.zone_temp:.1f}°F, Mode: {vav.mode}, " +
                      f"Airflow: {vav.current_airflow:.0f} CFM")
            
            # Increment time by one minute for the next simulation step
            current_minute_of_day += 1
            
            # Sleep for the appropriate time to maintain simulation speed
            await asyncio.sleep(sleep_time)
            
    except asyncio.CancelledError:
        print(f"\nSimulation for {vav.name} cancelled.")
    except Exception as e:
        print(f"\nError in {vav.name} simulation: {e}")
    finally:
        print(f"Simulation for {vav.name} stopped at {hour:02d}:{minute:02d}.")


async def simulate_ahu(ahu, app, weather_data, vav_boxes, minutes_per_second=1, start_time=(6, 0)):
    """Simulate an Air Handling Unit responding to VAV box demands."""
    current_hour, current_minute = start_time
    current_minute_of_day = current_hour * 60 + current_minute
    
    # Calculate sleep time for simulation speed
    sleep_time = 1 / minutes_per_second  # seconds per simulated minute
    
    print(f"\nStarting simulation for AHU {ahu.name}...")
    
    try:
        while not exit_event.is_set():
            # Get current simulation time
            current_minute_of_day = current_minute_of_day % 1440  # Wrap around at end of day
            hour = current_minute_of_day // 60
            minute = current_minute_of_day % 60
            
            # Get weather for current minute
            weather = weather_data[current_minute_of_day]
            outdoor_temp = weather["temperature"]
            
            # Calculate the current load from VAV boxes
            total_airflow = 0
            cooling_demand = 0
            heating_demand = 0
            
            for vav in vav_boxes:
                total_airflow += vav.current_airflow
                if vav.mode == "cooling":
                    cooling_demand += vav.current_airflow / vav.max_airflow
                elif vav.mode == "heating":
                    heating_demand += vav.reheat_valve_position
            
            # Normalize the demands
            if len(vav_boxes) > 0:
                cooling_demand /= len(vav_boxes)
                heating_demand /= len(vav_boxes)
            
            # Update AHU based on demands
            if cooling_demand > 0.1:
                # Adjust supply air temperature based on cooling demand
                # Higher demand = lower temperature (within limits)
                supply_air_temp = ahu.min_supply_air_temp + (1 - cooling_demand) * 5
                ahu.cooling_valve_position = cooling_demand
                ahu.heating_valve_position = 0
            elif heating_demand > 0.1:
                # Increase supply air temperature for heating loads
                supply_air_temp = ahu.max_supply_air_temp - (1 - heating_demand) * 5
                ahu.cooling_valve_position = 0
                ahu.heating_valve_position = heating_demand
            else:
                # Default supply air temperature in deadband
                supply_air_temp = ahu.supply_air_temp_setpoint
                ahu.cooling_valve_position = 0
                ahu.heating_valve_position = 0
            
            # Set current AHU state
            ahu.current_supply_air_temp = max(ahu.min_supply_air_temp, 
                                           min(ahu.max_supply_air_temp, supply_air_temp))
            ahu.current_total_airflow = total_airflow
            
            # Calculate energy usage
            # These would typically be more sophisticated calculations
            if ahu.cooling_valve_position > 0:
                # Cooling energy is proportional to airflow and temperature difference
                ahu.cooling_energy = ahu.current_total_airflow * 1.08 * \
                                     (outdoor_temp - ahu.current_supply_air_temp) * \
                                     ahu.cooling_valve_position
            else:
                ahu.cooling_energy = 0
                
            if ahu.heating_valve_position > 0:
                # Heating energy calculation
                ahu.heating_energy = ahu.current_total_airflow * 1.08 * \
                                    (ahu.current_supply_air_temp - outdoor_temp) * \
                                    ahu.heating_valve_position
            else:
                ahu.heating_energy = 0
            
            # Update the BACnet device
            if app:
                await ahu.update_bacnet_device()
                
            # Log data
            data_log[f"{ahu.name}_supply_temp"].append(ahu.current_supply_air_temp)
            data_log[f"{ahu.name}_airflow"].append(ahu.current_total_airflow)
            data_log[f"{ahu.name}_cooling"].append(ahu.cooling_valve_position)
            data_log[f"{ahu.name}_heating"].append(ahu.heating_valve_position)
            
            # Display current simulation time and key values
            # Only print updates every 5 minutes to reduce console output
            if minute % 5 == 0:
                time_str = f"{hour:02d}:{minute:02d}"
                cooling_status = f"Cooling: {ahu.cooling_valve_position*100:.0f}%" if ahu.cooling_valve_position > 0 else ""
                heating_status = f"Heating: {ahu.heating_valve_position*100:.0f}%" if ahu.heating_valve_position > 0 else ""
                print(f"{ahu.name} - Time: {time_str}, Supply: {ahu.current_supply_air_temp:.1f}°F, " + 
                      f"Airflow: {ahu.current_total_airflow:.0f} CFM, {cooling_status} {heating_status}")
            
            # Update VAV boxes with new supply air temperature
            for vav in vav_boxes:
                vav.supply_air_temp = ahu.current_supply_air_temp
            
            # Increment time by one minute for the next simulation step
            current_minute_of_day += 1
            
            # Sleep for the appropriate time to maintain simulation speed
            await asyncio.sleep(sleep_time)
            
    except asyncio.CancelledError:
        print(f"\nSimulation for {ahu.name} cancelled.")
    except Exception as e:
        print(f"\nError in {ahu.name} simulation: {e}")
    finally:
        print(f"Simulation for {ahu.name} stopped.")


async def simulate_chilled_water_plant(chiller, cooling_tower, app_chiller, app_tower, 
                                      weather_data, ahus, minutes_per_second=1, start_time=(6, 0)):
    """Simulate a chilled water plant (chiller and cooling tower)."""
    current_hour, current_minute = start_time
    current_minute_of_day = current_hour * 60 + current_minute
    
    # Calculate sleep time for simulation speed
    sleep_time = 1 / minutes_per_second  # seconds per simulated minute
    
    print(f"\nStarting simulation for chilled water plant ({chiller.name} and {cooling_tower.name})...")
    
    try:
        while not exit_event.is_set():
            # Get current simulation time
            current_minute_of_day = current_minute_of_day % 1440  # Wrap around at end of day
            hour = current_minute_of_day // 60
            minute = current_minute_of_day % 60
            
            # Get weather for current minute
            weather = weather_data[current_minute_of_day]
            outdoor_temp = weather["temperature"]
            outdoor_humidity = weather["humidity"]
            
            # Calculate wet bulb temperature (important for cooling tower performance)
            wet_bulb = estimate_wet_bulb(outdoor_temp, outdoor_humidity)
            
            # Calculate total cooling load from AHUs
            total_cooling_load_btuh = 0
            for ahu in ahus:
                if ahu.cooling_type == "chilled_water":
                    total_cooling_load_btuh += max(0, ahu.cooling_energy)
            
            # Convert BTU/hr to tons (1 ton = 12,000 BTU/hr)
            total_cooling_load_tons = total_cooling_load_btuh / 12000
            
            # Update cooling tower based on chiller needs
            if chiller.cooling_type == "water_cooled":
                # Connect the cooling tower to the chiller
                chiller.connect_cooling_tower(cooling_tower)
                
                # Update cooling tower with current outdoor conditions
                cooling_tower.update_load(
                    load=total_cooling_load_tons,
                    entering_water_temp=95,  # Typical return temp from chiller
                    ambient_wet_bulb=wet_bulb,
                    condenser_water_flow=max(100.0, total_cooling_load_tons * 3)  # 3 GPM/ton is typical
                )
                
                # Get the condenser water supply temperature from the cooling tower
                condenser_water_supply_temp = cooling_tower.get_condenser_water_supply_temp()
                
                # Update chiller with current load and conditions
                chiller.update_load(
                    load=total_cooling_load_tons,
                    entering_chilled_water_temp=54,  # Typical return from building
                    chilled_water_flow=max(100.0, total_cooling_load_tons * 2.4),  # 2.4 GPM/ton is typical
                    ambient_wet_bulb=wet_bulb,
                    ambient_dry_bulb=outdoor_temp
                )
            else:
                # Air-cooled chiller doesn't use cooling tower
                chiller.update_load(
                    load=total_cooling_load_tons,
                    entering_chilled_water_temp=54,  # Typical return from building
                    chilled_water_flow=max(100.0, total_cooling_load_tons * 2.4),
                    ambient_wet_bulb=wet_bulb,
                    ambient_dry_bulb=outdoor_temp
                )
            
            # Update the BACnet devices
            if app_chiller:
                await chiller.update_bacnet_device()
            if app_tower:
                await cooling_tower.update_bacnet_device()
                
            # Log data
            data_log[f"{chiller.name}_load"].append(chiller.current_load)
            data_log[f"{chiller.name}_cop"].append(chiller.current_cop)
            # Calculate power consumption if attribute doesn't exist
            power = getattr(chiller, 'current_power', 0)
            if power == 0 and hasattr(chiller, 'calculate_power_consumption'):
                power = chiller.calculate_power_consumption()
            data_log[f"{chiller.name}_power"].append(power)
            
            if cooling_tower:
                data_log[f"{cooling_tower.name}_approach"].append(cooling_tower.current_approach)
                data_log[f"{cooling_tower.name}_fan_speed"].append(cooling_tower.fan_speed)
            
            # Display current simulation time and key values
            # Only print updates every 5 minutes to reduce console output
            if minute % 5 == 0:
                time_str = f"{hour:02d}:{minute:02d}"
                # Calculate power consumption if attribute doesn't exist
                power = getattr(chiller, 'current_power', 0)
                if power == 0 and hasattr(chiller, 'calculate_power_consumption'):
                    power = chiller.calculate_power_consumption()
                
                print(f"Chilled Water Plant - Time: {time_str}, Load: {total_cooling_load_tons:.1f} tons, " + 
                      f"COP: {chiller.current_cop:.2f}, Power: {power:.1f} kW")
                
                # If we have a cooling tower, show its status
                if cooling_tower:
                    print(f"Cooling Tower - Approach: {cooling_tower.current_approach:.1f}°F, " + 
                          f"Fan: {cooling_tower.fan_speed:.0f}%, " + 
                          f"Supply: {cooling_tower.get_condenser_water_supply_temp():.1f}°F")
            
            # Increment time by one minute for the next simulation step
            current_minute_of_day += 1
            
            # Sleep for the appropriate time to maintain simulation speed
            await asyncio.sleep(sleep_time)
            
    except asyncio.CancelledError:
        print("\nSimulation for chilled water plant cancelled.")
    except Exception as e:
        print(f"\nError in chilled water plant simulation: {e}")
    finally:
        print("Simulation for chilled water plant stopped.")


async def shutdown():
    """Clean shutdown of the application."""
    global exit_event, all_devices
    
    # Signal all tasks to exit
    if exit_event and not exit_event.is_set():
        print("\nShutting down...")
        exit_event.set()
    
    # Close all BACnet devices if using BACpypes
    if all_devices:
        for app in all_devices:
            try:
                device_name = "unknown"
                device_id = 0
                
                # Find the device object
                for obj in app.objectIdentifier.values():
                    if hasattr(obj, "objectIdentifier") and obj.objectIdentifier[0] == "device":
                        device_name = getattr(obj, "objectName", "unknown")
                        device_id = obj.objectIdentifier[1]
                        break
                        
                print(f"Cleaning up BACnet device: {device_name} (ID: {device_id})")
                app.close()
                all_devices.remove(app)
                
            except Exception as e:
                print(f"Error during device cleanup: {e}")
    
    print("Shutdown complete.")


async def create_vav_from_schema(vav_data, device_id_base=1000):
    """Create a VAV box based on BRICK schema data."""
    # Extract room name from the VAV name
    room_id = vav_data.get("feeds", [""])[0]
    
    # Determine if this VAV has reheat 
    has_reheat = vav_data.get("has_reheat", False)
    
    # Determine VAV parameters based on type and zone
    # These are reasonable defaults - in a real system they would be extracted from BMS databases
    min_airflow = random.uniform(150, 250)  # Realistic low end for a VAV box
    max_airflow = random.uniform(1000, 1800)  # Realistic high end
    zone_temp_setpoint = random.uniform(70, 73)  # Standard office setpoints
    
    # Create the VAV box with these parameters
    vav = VAVBox(
        name=vav_data["id"],
        min_airflow=min_airflow,
        max_airflow=max_airflow,
        zone_temp_setpoint=zone_temp_setpoint,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=has_reheat,
        zone_area=random.uniform(800, 1200),  # Reasonable office zone size
        zone_volume=random.uniform(8000, 12000),  # Assuming 10ft ceilings
        window_area=random.uniform(80, 150),  # Reasonable window area
        window_orientation=random.choice(["north", "south", "east", "west"]),
        thermal_mass=random.uniform(1.5, 2.5)  # Medium to high thermal mass
    )
    
    return vav


async def main():
    global all_devices, virtual_network, controller_app, exit_event, start_time
    
    # Record start time
    start_time = time.time()
    
    # Create an exit event for clean shutdown
    exit_event = asyncio.Event()
    
    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    
    try:
        # Check if we have rdflib available
        if not RDFLIB_AVAILABLE:
            print("ERROR: rdflib is required to parse BRICK schema files.")
            return
        
        # Parse the BRICK schema file
        print("Parsing BRICK schema file: bldg1.ttl")
        parser = BrickParser("app/data/brick_schemas/bldg36.ttl")
        building_structure = parser.extract_all_equipment()
        
        print("\nExtracted building structure:")
        print(f"Building: {building_structure['building'].get('name', 'Unknown')}")
        print(f"AHUs: {len(building_structure['ahus'])} units")
        print(f"VAVs: {len(building_structure['vavs'])} boxes")
        print(f"Zones: {len(building_structure['zones'])} zones")
        print(f"Chillers: {len(building_structure['chillers'])} chillers")
        
        # Generate weather data for simulation with minute resolution
        weather_data = generate_weather_data(season="winter", minute_resolution=True)
        print("Generated 24-hour weather data with minute resolution for simulation")
        
        # Create virtual BACnet network if BACpypes is available
        if BACPYPES_AVAILABLE:
            network_name = "hvac-network"
            print(f"Creating virtual BACnet network: {network_name}")
            virtual_network = VirtualNetwork(network_name)
            print(f"Network created successfully: {virtual_network}")
            
            # Create a controller device
            controller_app = await create_building_controller(network_name)
            if controller_app:
                all_devices.append(controller_app)  # Keep reference for cleanup
        else:
            print("Running in simulation-only mode (without BACnet)")
        
        # Create a building object
        building_info = building_structure["building"]
        building = Building(
            name=building_info.get("name", "Office Building"),
            location="Chicago, IL",  # Default location
            latitude=41.8781,  # Chicago coordinates
            longitude=-87.6298,
            floor_area=building_info.get("area", 50000),
            num_floors=1,  # Default to 1 floor
            orientation=0,  # North-facing
            year_built=2005,
            timezone="America/Chicago"
        )
        
        if BACPYPES_AVAILABLE:
            building.create_bacpypes3_device(
                device_id=10000,
                device_name="Building Controller",
                network_interface_name=network_name,
                mac_address="0x0ACE"
            )
        
        # Create the VAV boxes based on BRICK schema
        vav_boxes = []
        vav_apps = []
        vav_devices = []  # Tuples of (vav, app)
        device_id_base = 1000
        
        print("\nCreating VAV boxes based on schema:")
        for vav_id, vav_data in building_structure["vavs"].items():
            print(f"Creating VAV box: {vav_id}")
            vav = await create_vav_from_schema(vav_data, device_id_base)
            vav_boxes.append(vav)
            
            # Add to building
            building.add_zone(vav)
            
            # Create BACnet device if available
            if BACPYPES_AVAILABLE:
                device_id = device_id_base + len(vav_boxes)
                mac_address = f"0x{device_id:x}"
                
                app = vav.create_bacpypes3_device(
                    device_id=device_id,
                    device_name=f"VAV-{vav.name}",
                    network_interface_name=network_name,
                    mac_address=mac_address
                )
                if app:
                    vav_apps.append(app)
                    all_devices.append(app)
                    vav_devices.append((vav, app))
        
        # Create AHUs based on BRICK schema
        all_ahus = []
        ahu_apps = []
        
        print("\nCreating AHUs based on schema:")
        device_id = 2000
        
        for ahu_id, ahu_data in building_structure["ahus"].items():
            # Determine which VAV boxes are fed by this AHU
            vav_list = []
            for vav_id in ahu_data["feeds"]:
                vav = next((v for v in vav_boxes if v.name == vav_id), None)
                if vav:
                    vav_list.append(vav)
            
            # Create the AHU with appropriate configuration
            print(f"Creating AHU: {ahu_id} with {len(vav_list)} VAV boxes")
            
            ahu = AirHandlingUnit(
                name=ahu_id,
                cooling_type="chilled_water",
                supply_air_temp_setpoint=55,
                min_supply_air_temp=52,
                max_supply_air_temp=65,
                max_supply_airflow=sum(vav.max_airflow for vav in vav_list) * 1.2,  # 20% safety factor
                vav_boxes=vav_list,
                enable_supply_temp_reset=True
            )
            
            # Create BACnet device if available
            if BACPYPES_AVAILABLE:
                mac_address = f"0x{device_id:x}"
                
                ahu_app = ahu.create_bacpypes3_device(
                    device_id=device_id,
                    device_name=f"AHU-{ahu.name}",
                    network_interface_name=network_name,
                    mac_address=mac_address
                )
                ahu_apps.append(ahu_app)
                all_devices.append(ahu_app)
            
            # Add to our list
            all_ahus.append(ahu)
            
            # Add to building
            building.add_air_handling_unit(ahu)
            
            # Increment device ID for next AHU
            device_id += 1
        
        # Create cooling plant based on chillers in BRICK schema
        chiller_data = next(iter(building_structure["chillers"].values()), None)
        
        if chiller_data:
            print(f"\nCreating cooling plant with chiller: {chiller_data['id']}")
            
            # Create cooling tower
            cooling_tower = CoolingTower(
                name="CT-1",
                capacity=400,  # tons
                design_approach=5,  # °F
                design_range=10,  # °F
                design_wet_bulb=78,  # °F
                min_speed=20,  # %
                tower_type="counterflow",
                fan_power=40,  # kW
                num_cells=2
            )
            
            # Create chiller
            chiller = Chiller(
                name=chiller_data["id"],
                cooling_type="water_cooled",
                capacity=350,  # tons
                design_cop=6.0,
                design_entering_condenser_temp=85,  # °F
                design_leaving_chilled_water_temp=44,  # °F
                min_part_load_ratio=0.1,
                design_chilled_water_flow=800,  # GPM
                design_condenser_water_flow=1200  # GPM
            )
            
            # Create BACnet devices for chiller and cooling tower
            if BACPYPES_AVAILABLE:
                chiller_app = chiller.create_bacpypes3_device(
                    device_id=device_id,
                    device_name=f"Chiller-{chiller.name}",
                    network_interface_name=network_name,
                    mac_address=f"0x{device_id:x}"
                )
                device_id += 1
                
                cooling_tower_app = cooling_tower.create_bacpypes3_device(
                    device_id=device_id,
                    device_name=f"CoolingTower-{cooling_tower.name}",
                    network_interface_name=network_name,
                    mac_address=f"0x{device_id:x}"
                )
                device_id += 1
                
                all_devices.append(chiller_app)
                all_devices.append(cooling_tower_app)
            else:
                chiller_app = None
                cooling_tower_app = None
            
            # Connect the cooling plant components
            chiller.connect_cooling_tower(cooling_tower)
        else:
            # Default cooling plant if none in schema
            print("\nNo chiller found in schema, creating default cooling plant")
            
            cooling_tower = CoolingTower(
                name="CT-1",
                capacity=400,
                design_approach=5,
                design_range=10,
                design_wet_bulb=78,
                min_speed=20,
                tower_type="counterflow",
                fan_power=40,
                num_cells=2
            )
            
            chiller = Chiller(
                name="Chiller-1",
                cooling_type="water_cooled",
                capacity=350,
                design_cop=6.0,
                design_entering_condenser_temp=85,
                design_leaving_chilled_water_temp=44,
                min_part_load_ratio=0.1,
                design_chilled_water_flow=800,
                design_condenser_water_flow=1200
            )
            
            # Default BACnet devices
            if BACPYPES_AVAILABLE:
                chiller_app = chiller.create_bacpypes3_device(
                    device_id=device_id,
                    device_name=f"Chiller-{chiller.name}",
                    network_interface_name=network_name,
                    mac_address=f"0x{device_id:x}"
                )
                device_id += 1
                
                cooling_tower_app = cooling_tower.create_bacpypes3_device(
                    device_id=device_id,
                    device_name=f"CoolingTower-{cooling_tower.name}",
                    network_interface_name=network_name,
                    mac_address=f"0x{device_id:x}"
                )
                device_id += 1
                
                all_devices.append(chiller_app)
                all_devices.append(cooling_tower_app)
            else:
                chiller_app = None
                cooling_tower_app = None
            
            # Connect default cooling plant components
            chiller.connect_cooling_tower(cooling_tower)
        
        # Create a boiler for heating
        print("\nCreating boiler for heating system")
        boiler = Boiler(
            name="Boiler-1",
            fuel_type="gas",
            capacity=2000,  # MBH
            design_efficiency=0.92,
            design_entering_water_temp=160,  # °F
            design_leaving_water_temp=180,  # °F
            min_part_load_ratio=0.2,
            design_hot_water_flow=200,  # GPM
            condensing=True,
            turndown_ratio=5.0
        )
        
        # Create BACnet device for boiler
        if BACPYPES_AVAILABLE:
            boiler_app = boiler.create_bacpypes3_device(
                device_id=device_id,
                device_name=f"Boiler-{boiler.name}",
                network_interface_name=network_name,
                mac_address=f"0x{device_id:x}"
            )
            device_id += 1
            
            if boiler_app:
                all_devices.append(boiler_app)
        else:
            boiler_app = None
        
        # Define minutes per second for real-time simulation (1 minute of simulation time per 1 second of real time)
        simulation_speed = 1  # 1 minute per second
        
        # Start simulations for each equipment type
        simulation_tasks = []
        
        # Define common start time for all simulations
        start_time_tuple = (6, 0)  # 6:00 AM
        
        # Start VAV simulations
        print("\nStarting VAV box simulations...")
        for vav, app in vav_devices:
            simulation_tasks.append(
                asyncio.create_task(
                    simulate_vav_box(
                        vav, 
                        app, 
                        weather_data, 
                        minutes_per_second=simulation_speed, 
                        start_time=start_time_tuple
                    )
                )
            )
        
        # Start AHU simulations
        for i, ahu in enumerate(all_ahus):
            app = ahu_apps[i] if i < len(ahu_apps) else None
            
            simulation_tasks.append(
                asyncio.create_task(
                    simulate_ahu(
                        ahu, 
                        app, 
                        weather_data, 
                        ahu.vav_boxes, 
                        minutes_per_second=simulation_speed, 
                        start_time=start_time_tuple
                    )
                )
            )
        
        # Start chilled water plant simulation
        simulation_tasks.append(
            asyncio.create_task(
                simulate_chilled_water_plant(
                    chiller, 
                    cooling_tower, 
                    chiller_app, 
                    cooling_tower_app, 
                    weather_data, 
                    all_ahus, 
                    minutes_per_second=simulation_speed, 
                    start_time=start_time_tuple
                )
            )
        )
        
        # Wait for all tasks to complete or until interrupted
        await asyncio.gather(*simulation_tasks)
        
    except Exception as e:
        import traceback
        print(f"Error in main: {e}")
        traceback.print_exc()
    finally:
        # Clean shutdown
        await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This will be handled by the signal handler in main()
        pass
    except Exception as e:
        print(f"Unhandled exception: {e}")