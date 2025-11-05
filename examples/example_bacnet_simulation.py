#!/usr/bin/env python3
"""
Example of VAV Box simulation with BACnet integration using BACpypes3.
Runs an accelerated simulation at 1 hour per minute (60x speed).
"""

import time
import math
import random
from datetime import datetime, timedelta
import asyncio
import sys

from src.vav_box import VAVBox

# Create a VAV box with some configuration
vav = VAVBox(
    name="Office-1",
    min_airflow=100,  # CFM
    max_airflow=1000,  # CFM
    zone_temp_setpoint=72,  # °F
    deadband=2,  # °F
    discharge_air_temp_setpoint=55,  # °F
    has_reheat=True,
    zone_area=400,  # sq ft
    zone_volume=3200,  # cubic ft (8ft ceiling)
    window_area=80,  # sq ft
    window_orientation="east",  # east-facing windows
    thermal_mass=2.0  # Medium thermal mass
)

# Setup simulation parameters
async def run_simulation():
    """Run the VAV simulation in an accelerated time mode."""
    print("\nStarting VAV simulation (1 hour per minute)...")

    # Create BACnet device from VAV box using BACpypes3
    # Use the container's IP address on the ace-iot network
    print("Creating BACpypes3 device...")
    device = vav.create_bacpypes3_device(ip_address="172.26.0.20/16")

    if device is None:
        print("Failed to create BACnet device")
        return

    print(f"Created BACnet device: {device.device_object.objectName} (Device ID: {device.device_object.objectIdentifier[1]})")

    # Display some of the BACnet points
    print("\nBACnet Points:")
    essential_points = ["zone_temp", "damper_position", "reheat_valve_position", "mode"]
    for point_name in essential_points:
        # Find the object by name
        for obj in device.objectIdentifier.values():
            if hasattr(obj, "objectName") and obj.objectName == point_name:
                print(f"- {point_name}: {obj.presentValue} ({obj.objectType})")
                break

    # Define a 24-hour period of outdoor temperatures with a sine wave pattern
    # Coldest at 5 AM, warmest at 5 PM
    outdoor_temps = {hour: 65 + 15 * math.sin(math.pi * (hour - 5) / 12) for hour in range(24)}
    
    # Office occupied from 8 AM to 6 PM
    occupied_hours = [(8, 18)]
    occupancy = 5  # 5 people during occupied hours
    
    # Simulation start time - 6 AM
    start_hour = 6
    current_hour = start_hour
    
    # Constant AHU supply air temperature
    supply_air_temp = 55  # °F
    
    try:
        # Run continuous simulation with 1 minute = 1 hour acceleration
        while True:
            # Get current simulation hour (wrapped to 0-23)
            hour = current_hour % 24
            minute = 0
            
            # Get temperature for current hour
            outdoor_temp = outdoor_temps[hour]
            
            # Check if occupied based on time of day
            is_occupied = any(start <= hour < end for start, end in occupied_hours)
            occupancy_count = occupancy if is_occupied else 0
            
            # Add some random variation to make it more realistic
            outdoor_temp += random.uniform(-1, 1)  # ±1°F variation
            
            # Set occupancy
            vav.set_occupancy(occupancy_count)
            
            # Update VAV box with current conditions
            vav.update(vav.zone_temp, supply_air_temp)
            
            # Simulate thermal behavior for 1 hour
            vav_effect = 0
            if vav.mode == "cooling":
                vav_effect = vav.current_airflow / vav.max_airflow
            elif vav.mode == "heating" and vav.has_reheat:
                vav_effect = -vav.reheat_valve_position
                
            temp_change = vav.calculate_thermal_behavior(
                minutes=60,  # 1 hour
                outdoor_temp=outdoor_temp,
                vav_cooling_effect=vav_effect,
                time_of_day=(hour, minute)
            )
            
            # Update zone temperature with calculated change
            vav.zone_temp += temp_change

            # Update the BACnet device
            await vav.update_bacnet_device()

            # Display current simulation time and key values
            time_str = f"{hour:02d}:{minute:02d}"
            print(f"Time: {time_str}, Outdoor: {outdoor_temp:.1f}°F, " + 
                  f"Zone: {vav.zone_temp:.1f}°F, Mode: {vav.mode}, " +
                  f"Airflow: {vav.current_airflow:.0f} CFM")
            
            # Move to next hour
            current_hour += 1
            
            # Sleep for 1 minute real time = 1 hour sim time
            # Use asyncio.sleep to properly yield to the event loop
            await asyncio.sleep(60)
            
    except asyncio.CancelledError:
        print("\nSimulation task cancelled.")
    except Exception as e:
        print(f"\nError in simulation: {e}")
    finally:
        print("Simulation stopped.")

async def main():
    print("Initializing BACnet simulation...")

    # Create simulation task
    simulation_task = asyncio.create_task(run_simulation())

    print("\nPress Ctrl+C to stop the simulation")

    try:
        # Wait for the simulation task to complete (or be cancelled)
        await simulation_task
    except KeyboardInterrupt:
        print("\nCancelling simulation...")
        simulation_task.cancel()
        try:
            await simulation_task
        except asyncio.CancelledError:
            pass
    finally:
        print("Simulation complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")