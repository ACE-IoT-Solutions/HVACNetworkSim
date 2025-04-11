#!/usr/bin/env python3
"""
Complete HVAC System simulation with BACnet integration using BACpypes3.

This simulation demonstrates:
1. A full building model with VAV boxes, AHUs, chillers, cooling towers, and boilers
2. All equipment represented on a BACnet network using BACpypes3
3. Real-time visualization of equipment performance
4. Dynamic scheduling and control
5. Weather-based load simulation

The simulation runs in real-time (1 minute of simulation per 1 second) to show system behavior
with high temporal resolution.
"""

import asyncio
import math
import random
import signal
import sys
import time
from datetime import datetime, timedelta
from collections import defaultdict
import json
from pathlib import Path
from typing import List

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

from src.vav_box import VAVBox, PIDController
from src.ahu import AirHandlingUnit
from src.cooling_tower import CoolingTower
from src.chiller import Chiller
from src.boiler import Boiler
from src.building import Building

# Constants
IP_ADDRESS = "10.88.0.4"
IP_SUBNET_MASK = "255.255.0.0"

# Global references to keep objects alive
all_devices: List[Application] = []
virtual_network = None
controller_app = None
exit_event = None
data_log = defaultdict(list)  # For storing simulation data
start_time = None


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
        # Network Port
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

async def discover_devices(controller_app):
    """Discover devices on the network using Who-Is service."""
    if not BACPYPES_AVAILABLE:
        return []
        
    try:
        print("\nDiscovering devices on the network...")
        
        # Use Who-Is to discover devices with specific parameters to avoid excessive traffic
        # Limit the device range to reduce network traffic
        i_ams = await controller_app.who_is(low_limit=1, high_limit=10000)
        
        for i_am in i_ams:
            print(f"Found device: ID {i_am.iAmDeviceIdentifier[1]} at {i_am.pduSource}")
        
        return i_ams
    except Exception as e:
        print(f"Error discovering devices: {e}")
        return []

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
            
            # Humidity model (highest at night/morning, lowest in afternoon)
            humidity = 70 - 30 * math.sin(math.pi * (hour - 5) / 12)**2
            
            # Solar radiation (0 at night, peak at noon)
            if 7 <= hour <= 17:  # Daylight hours (adjust for season)
                solar_factor = math.sin(math.pi * (hour - 7) / 10)
                if season == "summer":
                    max_solar = 800  # Summer solar radiation peak
                elif season == "winter":
                    max_solar = 500  # Winter solar radiation peak
                else:
                    max_solar = 650  # Spring/fall
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

async def simulate_vav_box(vav, app, weather_data, minutes_per_second=1, start_time=(6, 0)):
    """Maintain an ongoing simulation of a VAV box, updating every minute."""
    current_hour, current_minute = start_time
    current_minute_of_day = current_hour * 60 + current_minute
    previous_time = (current_hour, current_minute)
    
    # Constant AHU supply air temperature
    supply_air_temp = vav.ahu_supply_air_temp  # °F
    
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
            
            # # Log data for later analysis
            # data_log["time"].append(f"{hour:02d}:{minute:02d}")
            # data_log[f"{vav.name}_temp"].append(vav.zone_temp)
            # data_log[f"{vav.name}_mode"].append(vav.mode)
            # data_log[f"{vav.name}_airflow"].append(vav.current_airflow)
            # data_log["outdoor_temp"].append(outdoor_temp)
            
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
                
            # # Log data
            # data_log[f"{ahu.name}_supply_temp"].append(ahu.current_supply_air_temp)
            # data_log[f"{ahu.name}_airflow"].append(ahu.current_total_airflow)
            # data_log[f"{ahu.name}_cooling"].append(ahu.cooling_valve_position)
            # data_log[f"{ahu.name}_heating"].append(ahu.heating_valve_position)
            
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
                    condenser_water_flow=max(100, total_cooling_load_tons * 3)  # 3 GPM/ton is typical
                )
                
                # Get the condenser water supply temperature from the cooling tower
                condenser_water_supply_temp = cooling_tower.get_condenser_water_supply_temp()
                
                # Update chiller with current load and conditions
                chiller.update_load(
                    load=total_cooling_load_tons,
                    entering_chilled_water_temp=54,  # Typical return from building
                    chilled_water_flow=max(100, total_cooling_load_tons * 2.4),  # 2.4 GPM/ton is typical
                    ambient_wet_bulb=wet_bulb,
                    ambient_dry_bulb=outdoor_temp
                )
            else:
                # Air-cooled chiller doesn't use cooling tower
                chiller.update_load(
                    load=total_cooling_load_tons,
                    entering_chilled_water_temp=54,  # Typical return from building
                    chilled_water_flow=max(100, total_cooling_load_tons * 2.4),
                    ambient_wet_bulb=wet_bulb,
                    ambient_dry_bulb=outdoor_temp
                )
            
            # Update the BACnet devices
            if app_chiller:
                await chiller.update_bacnet_device()
            if app_tower:
                await cooling_tower.update_bacnet_device()
                
            # Log data
            # data_log[f"{chiller.name}_load"].append(chiller.current_load)
            # data_log[f"{chiller.name}_cop"].append(chiller.current_cop)
            # Calculate power consumption if attribute doesn't exist
            power = getattr(chiller, 'current_power', 0)
            if power == 0 and hasattr(chiller, 'calculate_power_consumption'):
                power = chiller.calculate_power_consumption()
            # data_log[f"{chiller.name}_power"].append(power)
            
            # if cooling_tower:
            #     data_log[f"{cooling_tower.name}_approach"].append(cooling_tower.current_approach)
            #     data_log[f"{cooling_tower.name}_fan_speed"].append(cooling_tower.fan_speed)
            
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

async def simulate_hot_water_plant(boiler, app_boiler, weather_data, vav_boxes, minutes_per_second=1, start_time=(6, 0)):
    """Simulate a hot water plant (boiler)."""
    current_hour, current_minute = start_time
    current_minute_of_day = current_hour * 60 + current_minute
    
    # Calculate sleep time for simulation speed
    sleep_time = 1 / minutes_per_second  # seconds per simulated minute
    
    print(f"\nStarting simulation for hot water plant ({boiler.name})...")
    
    try:
        while not exit_event.is_set():
            # Get current simulation time
            current_minute_of_day = current_minute_of_day % 1440  # Wrap around at end of day
            hour = current_minute_of_day // 60
            minute = current_minute_of_day % 60
            
            # Get weather for current minute
            weather = weather_data[current_minute_of_day]
            outdoor_temp = weather["temperature"]
            
            # Calculate total heating load from VAV boxes (reheat)
            total_heating_load_btuh = 0
            for vav in vav_boxes:
                if vav.has_reheat and vav.reheat_valve_position > 0:
                    # Sum up heating energy from all VAVs with active reheat
                    total_heating_load_btuh += vav.heating_energy
            
            # Convert BTU/hr to MBH (thousand BTU/hr)
            total_heating_load_mbh = total_heating_load_btuh / 1000
            
            # Update boiler with current load and conditions
            boiler.update_load(
                load=total_heating_load_mbh,
                entering_water_temp=160,  # Typical return from building
                hot_water_flow=max(20, total_heating_load_mbh / 20),  # Flow rate (GPM)
                ambient_temp=75  # Indoor mechanical room temperature
            )
            
            # Update the BACnet device
            if app_boiler:
                await boiler.update_bacnet_device()
                
            # Log data
            # data_log[f"{boiler.name}_load"].append(boiler.current_load)
            # data_log[f"{boiler.name}_efficiency"].append(boiler.current_efficiency)
            
            # Display current simulation time and key values
            # Only print updates every 5 minutes to reduce console output
            if minute % 5 == 0:
                time_str = f"{hour:02d}:{minute:02d}"
                print(f"Hot Water Plant - Time: {time_str}, Load: {total_heating_load_mbh:.1f} MBH, " + 
                      f"Efficiency: {boiler.current_efficiency*100:.1f}%, " + 
                      f"Fuel: {boiler.calculate_fuel_consumption()}")
            
            # Increment time by one minute for the next simulation step
            current_minute_of_day += 1
            
            # Sleep for the appropriate time to maintain simulation speed
            await asyncio.sleep(sleep_time)
            
    except asyncio.CancelledError:
        print("\nSimulation for hot water plant cancelled.")
    except Exception as e:
        print(f"\nError in hot water plant simulation: {e}")
    finally:
        print("Simulation for hot water plant stopped.")

async def read_device_property(controller_app, device_address, object_id, property_id):
    """Helper function to read a property with better error handling."""
    if not BACPYPES_AVAILABLE:
        return None
        
    try:
        # Add a short timeout to avoid hanging
        return await asyncio.wait_for(
            controller_app.read_property(
                address=device_address,
                objectIdentifier=object_id,
                propertyIdentifier=property_id
            ),
            timeout=2.0
        )
    except asyncio.TimeoutError:
        print(f"Timeout reading {property_id} from {object_id}")
        return None
    except Exception as e:
        print(f"Error reading {property_id} from {object_id}: {e}")
        return None

async def controller_monitoring(controller_app, monitoring_interval=10):
    """Periodically monitor HVAC devices from the controller."""
    if not BACPYPES_AVAILABLE or controller_app is None:
        return
        
    try:
        discovered_devices = []
        
        # Initial discovery
        print("\nInitial device discovery...")
        i_ams = await discover_devices(controller_app)
        discovered_devices = i_ams
        
        # Periodic monitoring
        while not exit_event.is_set():
            try:
                # Every interval, read the latest state from a few random devices
                print("\n--- BMS Controller Monitoring Update ---")
                
                # Re-discover devices occasionally to catch any changes
                if random.random() < 0.2:  # 20% chance to rediscover
                    # Use a longer interval between discoveries
                    await asyncio.sleep(0.5)
                    i_ams = await discover_devices(controller_app)
                    discovered_devices = i_ams
                
                # Read state from a few random devices (to reduce output noise)
                if discovered_devices:
                    sample_size = min(2, len(discovered_devices))  # Reduced from 3 to 2
                    sample_devices = random.sample(discovered_devices, sample_size)
                    
                    for i_am in sample_devices:
                        device_id = i_am.iAmDeviceIdentifier[1]
                        device_address = i_am.pduSource
                        
                        # Add a delay between device queries to prevent flooding
                        await asyncio.sleep(0.5)
                        
                        try:
                            # Read the device object to get its name
                            device_obj = await read_device_property(
                                controller_app,
                                device_address,
                                f"device,{device_id}",
                                "object-name"
                            )
                            
                            if device_obj is None:
                                continue
                                
                            print(f"\nReading state of device {device_id} ({device_obj}):")
                            
                            # Sample a few random properties from the device
                            # Add delay to prevent flooding
                            await asyncio.sleep(0.2)
                            
                            object_list = await read_device_property(
                                controller_app,
                                device_address,
                                f"device,{device_id}",
                                "object-list"
                            )
                            
                            # Choose a few random objects to read
                            if object_list:
                                # Reduce the number of sampled objects
                                sample_obj_count = min(3, len(object_list))
                                sample_objects = random.sample(object_list, sample_obj_count)
                                
                                for obj_id in sample_objects:
                                    # Add delay between object reads
                                    await asyncio.sleep(0.2)
                                    
                                    # Read the object name
                                    obj_name = await read_device_property(
                                        controller_app,
                                        device_address,
                                        obj_id,
                                        "object-name"
                                    )
                                    
                                    if obj_name is None:
                                        continue
                                    
                                    # Read the present value
                                    await asyncio.sleep(0.2)
                                    present_value = await read_device_property(
                                        controller_app,
                                        device_address,
                                        obj_id,
                                        "present-value"
                                    )
                                    
                                    if present_value is not None:
                                        print(f"  {obj_name}: {present_value}")
                                        
                        except Exception as e:
                            print(f"Error reading device {device_id}: {e}")
            except Exception as e:
                print(f"Controller monitoring error: {e}")
                
            # Wait before next monitoring cycle - increased to reduce network load
            await asyncio.sleep(monitoring_interval)
            
    except asyncio.CancelledError:
        print("\nController monitoring cancelled.")
    except Exception as e:
        print(f"\nError in controller monitoring: {e}")
    finally:
        print("Controller monitoring stopped.")

# async def write_data_log():
#     """Write the data log to a JSON file when the simulation ends."""
#     global data_log, start_time
    
#     if data_log:
#         try:
#             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#             filename = f"simulation_data_{timestamp}.json"
            
#             with open(filename, 'w') as f:
#                 json.dump(data_log, f, indent=2)
                
#             print(f"\nSimulation data written to {filename}")
            
#             # Also write a simple summary report
#             simulation_duration = time.time() - start_time if start_time else 0
            
#             summary = {
#                 "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#                 "duration_seconds": round(simulation_duration, 1),
#                 "data_points_collected": len(data_log["time"]) if "time" in data_log else 0,
#                 "equipment_simulated": [key.split('_')[0] for key in data_log.keys() 
#                                        if '_' in key and key.split('_')[1] in 
#                                        ('temp', 'load', 'cop', 'airflow')]
#             }
            
#             summary_filename = f"simulation_summary_{timestamp}.json"
#             with open(summary_filename, 'w') as f:
#                 json.dump(summary, f, indent=2)
                
#             print(f"Simulation summary written to {summary_filename}")
            
#         except Exception as e:
#             print(f"Error writing data log: {e}")

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
                        
                print(f"Cleaning up BACnet device: {device_name} (ID: {device_id}) : {app.device_object}")
                app.close()
                all_devices.remove(app)
                
                # BACpypes3 handles cleanup automatically when Python objects are garbage collected
                # No explicit close() method needed
            except Exception as e:
                print(f"Error during device cleanup: {e}")
    
    # Write data log
    # await write_data_log()
    
    print("Shutdown complete.")

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
        
        # Create a building
        building = Building(
            name="Office Building",
            location="Chicago, IL",
            latitude=41.8781,
            longitude=-87.6298,
            floor_area=50000,
            num_floors=3,
            orientation=0,  # North-facing
            year_built=2005,
            timezone="America/Chicago"
        )
        building.create_bacpypes3_device(
            device_id = 10000,
            device_name = "Building Controller",
            network_interface_name = network_name,
            mac_address = "0x0ACE"
        )
        
        # Create VAV boxes for different zones
        vav_configs = [
            {
                "name": "Office-North",
                "min_airflow": 200,
                "max_airflow": 1500,
                "zone_temp_setpoint": 72,
                "deadband": 2,
                "discharge_air_temp_setpoint": 55,
                "has_reheat": True,
                "zone_area": 800,
                "zone_volume": 8000,
                "window_area": 120,
                "window_orientation": "north",
                "thermal_mass": 2.0,
                "device_id": 1001,
                "mac_address": "0x10"
            },
            {
                "name": "Office-East",
                "min_airflow": 180,
                "max_airflow": 1200,
                "zone_temp_setpoint": 72,
                "deadband": 2,
                "discharge_air_temp_setpoint": 55,
                "has_reheat": True,
                "zone_area": 600,
                "zone_volume": 6000,
                "window_area": 100,
                "window_orientation": "east",
                "thermal_mass": 1.8,
                "device_id": 1002,
                "mac_address": "0x11"
            },
            {
                "name": "Conference",
                "min_airflow": 300,
                "max_airflow": 2000,
                "zone_temp_setpoint": 70,
                "deadband": 2,
                "discharge_air_temp_setpoint": 55,
                "has_reheat": True,
                "zone_area": 1000,
                "zone_volume": 10000,
                "window_area": 200,
                "window_orientation": "south",
                "thermal_mass": 1.5,
                "device_id": 1003,
                "mac_address": "0x12"
            },
            {
                "name": "Lobby",
                "min_airflow": 500,
                "max_airflow": 3000,
                "zone_temp_setpoint": 73,
                "deadband": 3,
                "discharge_air_temp_setpoint": 58,
                "has_reheat": False,
                "zone_area": 1500,
                "zone_volume": 18000,
                "window_area": 400,
                "window_orientation": "west",
                "thermal_mass": 3.0,
                "device_id": 1004,
                "mac_address": "0x13"
            }
        ]
        
        # Create VAV boxes and BACnet devices
        vav_boxes = []
        vav_apps = []
        vav_devices = []  # Tuples of (vav, app)
        next_device_id = 2000  # Starting ID for equipment
        
        for config in vav_configs:
            device_id = config.pop("device_id", None)
            mac_address = config.pop("mac_address", None)
            
            # Create the VAV box
            vav = VAVBox(**config)
            vav_boxes.append(vav)
            
            # Add to building
            building.add_zone(vav)
            
            # Create BACnet device
            if device_id and mac_address:
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
                vav.device_object = app  # Store the BACnet device object in the VAV box
        
        # Create AHUs
        ahu1 = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=8000,
            vav_boxes=vav_boxes[:3],  # First 3 VAVs
            enable_supply_temp_reset=True
        )
        
        ahu2 = AirHandlingUnit(
            name="AHU-2",
            cooling_type="dx",
            supply_air_temp_setpoint=58,
            min_supply_air_temp=55,
            max_supply_air_temp=65,
            max_supply_airflow=4000,
            vav_boxes=vav_boxes[3:],  # Lobby only
            enable_supply_temp_reset=True,
            compressor_stages=2
        )
        
        # Add methods to AHU for BACnet compatibility
        # def get_ahu_process_variables(self):
        #     """Return a dictionary of all process variables for the AHU."""
        #     variables = {
        #         "name": self.name,
        #         "supply_air_temp": self.current_supply_air_temp,
        #         "supply_air_temp_setpoint": self.supply_air_temp_setpoint,
        #         "total_airflow": self.current_total_airflow,
        #         "cooling_valve_position": self.cooling_valve_position,
        #         "heating_valve_position": self.heating_valve_position,
        #         "cooling_type": self.cooling_type,
        #         "cooling_energy": self.cooling_energy if hasattr(self, 'cooling_energy') else 0,
        #         "heating_energy": self.heating_energy if hasattr(self, 'heating_energy') else 0,
        #         "max_supply_airflow": self.max_supply_airflow
        #     }
        #     return variables
        
        # Add the methods to the AHU class
        # AirHandlingUnit.get_process_variables = get_ahu_process_variables
        
        # Create BACnet devices for AHUs
        ahu_apps = []
        for ahu in [ahu1, ahu2]:
            ahu_app = ahu.create_bacpypes3_device(
                device_id=next_device_id,
                device_name=f"AHU-{ahu.name}",
                network_interface_name=network_name,
                mac_address=f"0x{next_device_id:x}"
            )
            ahu_apps.append(ahu_app)
            all_devices.append(ahu_app)
            next_device_id += 1
        
        # Add AHUs to building
        building.add_air_handling_unit(ahu1)
        building.add_air_handling_unit(ahu2)
        
        # Create cooling plant
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
        
        chiller = Chiller(
            name="Chiller-1",
            cooling_type="water_cooled",
            capacity=350,  # tons
            design_cop=6.0,
            design_entering_condenser_temp=85,  # °F
            design_leaving_chilled_water_temp=44,  # °F
            min_part_load_ratio=0.1,
            design_chilled_water_flow=800,  # GPM
            design_condenser_water_flow=1200  # GPM
        )
        
        # Add methods to Chiller and CoolingTower for BACnet compatibility
        # def get_chiller_process_variables(self):
        #     """Return a dictionary of all process variables for the chiller."""
        #     return {
        #         "name": self.name,
        #         "cooling_type": self.cooling_type,
        #         "capacity": self.capacity,
        #         "current_load": self.current_load,
        #         "current_cop": self.current_cop,
        #         "current_power": self.current_power,
        #         "chilled_water_flow": self.chilled_water_flow,
        #         "condenser_water_flow": self.condenser_water_flow if hasattr(self, 'condenser_water_flow') else 0,
        #         "leaving_chilled_water_temp": self.leaving_chilled_water_temp,
        #         "entering_condenser_temp": self.entering_condenser_temp if hasattr(self, 'entering_condenser_temp') else 0
        #     }
        
        # def get_cooling_tower_process_variables(self):
        #     """Return a dictionary of all process variables for the cooling tower."""
        #     return {
        #         "name": self.name,
        #         "capacity": self.capacity,
        #         "fan_speed_percent": self.fan_speed,
        #         "current_approach": self.current_approach,
        #         "current_range": self.current_range,
        #         "current_load": self.current_load,
        #         "outdoor_wet_bulb": self.outdoor_wet_bulb,
        #         # "outdoor_dry_bulb": self.outdoor_dry_bulb,
        #         "condenser_water_supply_temp": self.condenser_water_supply_temp,
        #         "condenser_water_return_temp": self.condenser_water_return_temp,
        #         "fan_power": self.fan_power
        #     }
        
        # Add the methods to the classes
        # Chiller.get_process_variables = get_chiller_process_variables
        # CoolingTower.get_process_variables = get_cooling_tower_process_variables
        
        # Create BACnet devices for chiller and cooling tower
        chiller_app = chiller.create_bacpypes3_device(
            device_id=next_device_id,
            device_name=f"Chiller-{chiller.name}",
            network_interface_name=network_name,
            mac_address=f"0x{next_device_id:x}"
        )
        next_device_id += 1
        cooling_tower_app = cooling_tower.create_bacpypes3_device(
            device_id=next_device_id + 1,
            device_name=f"CoolingTower-{cooling_tower.name}",
            network_interface_name=network_name,
            mac_address=f"0x{next_device_id + 1:x}"
        )
        next_device_id += 1
        all_devices.append(chiller_app)
        all_devices.append(cooling_tower_app)
        
        # Create hot water plant
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
        
        # Add methods to Boiler for BACnet compatibility
        # def get_boiler_process_variables(self):
        #     """Return a dictionary of all process variables for the boiler."""
        #     return {
        #         "name": self.name,
        #         "fuel_type": self.fuel_type,
        #         "capacity": self.capacity,
        #         "current_load": self.current_load,
        #         "current_efficiency": self.current_efficiency,
        #         "leaving_water_temp": self.leaving_water_temp,
        #         "entering_water_temp": self.entering_water_temp,
        #         "hot_water_flow": self.hot_water_flow
        #     }
        
        # # Add the methods to the Boiler class
        # Boiler.get_process_variables = get_boiler_process_variables
        
        # Create BACnet device for boiler
        boiler_app = boiler.create_bacpypes3_device(
            device_id=next_device_id,
            device_name=f"Boiler-{boiler.name}",
            network_interface_name=network_name,
            mac_address=f"0x{next_device_id:x}"
        )
        next_device_id += 1
        
        if boiler_app:
            all_devices.append(boiler_app)
        
        # Connect the equipment
        chiller.connect_cooling_tower(cooling_tower)
        
        # Define minutes per second for real-time simulation (1 minute of simulation time per 1 second of real time)
        simulation_speed = 1  # 1 minute per second
        
        # Start simulations for each equipment type
        simulation_tasks = []
        
        # Define common start time for all simulations
        start_time = (6, 0)  # 6:00 AM
        
        # Start VAV simulations
        print("\nStarting VAV box simulations...")
        for vav, app in vav_devices:
            simulation_tasks.append(
                asyncio.create_task(
                    simulate_vav_box(vav, app, weather_data, minutes_per_second=simulation_speed, start_time=start_time)
                )
            )
        
        # Start AHU simulations
        simulation_tasks.append(
            asyncio.create_task(
                simulate_ahu(ahu1, ahu_apps[0] if ahu_apps else None, weather_data, 
                             ahu1.vav_boxes, minutes_per_second=simulation_speed, start_time=start_time)
            )
        )
        
        simulation_tasks.append(
            asyncio.create_task(
                simulate_ahu(ahu2, ahu_apps[1] if len(ahu_apps) > 1 else None, 
                             weather_data, ahu2.vav_boxes, minutes_per_second=simulation_speed, start_time=start_time)
            )
        )
        
        # Start chilled water plant simulation
        simulation_tasks.append(
            asyncio.create_task(
                simulate_chilled_water_plant(chiller, cooling_tower, chiller_app, 
                                            cooling_tower_app, weather_data, 
                                            [ahu1, ahu2], minutes_per_second=simulation_speed, start_time=start_time)
            )
        )
        
        # Start hot water plant simulation
        simulation_tasks.append(
            asyncio.create_task(
                simulate_hot_water_plant(boiler, boiler_app, weather_data, 
                                        vav_boxes, minutes_per_second=simulation_speed, start_time=start_time)
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