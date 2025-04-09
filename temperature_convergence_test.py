#!/usr/bin/env python3
"""
Script to visualize temperature convergence for VAV Box simulations.
"""

import sys
import math
import random
from pathlib import Path
import matplotlib.pyplot as plt
from unittest.mock import patch, MagicMock

# Mock the bacpypes3 module before importing VAVBox
sys.modules['bacpypes3'] = MagicMock()
sys.modules['bacpypes3.app'] = MagicMock()
sys.modules['bacpypes3.object'] = MagicMock()
sys.modules['bacpypes3.vlan'] = MagicMock()
sys.modules['bacpypes3.pdu'] = MagicMock()
sys.modules['bacpypes3.primitivedata'] = MagicMock()

from src.vav_box import VAVBox

def run_simulation(vav, supply_air_temp, outdoor_temps, iterations):
    """
    Run a simulation for the specified number of iterations.
    
    Args:
        vav: VAVBox instance
        supply_air_temp: Supply air temperature
        outdoor_temps: Dict mapping hour to outdoor temperature
        iterations: Number of iterations to run
        
    Returns:
        Dict with simulation results
    """
    results = {
        'zone_temps': [vav.zone_temp],
        'modes': ['initial'],
        'damper_positions': [0],
        'reheat_positions': [0],
        'hours': [12],
        'minutes': [0],
        'outdoor_temps': [outdoor_temps[12]]
    }
    
    current_hour = 12
    current_minute = 0
    
    # Ensure PID controllers are reset
    vav.cooling_pid.reset()
    vav.heating_pid.reset()
    
    for i in range(iterations):
        # Update hour and minute
        current_minute += 15
        if current_minute >= 60:
            current_hour = (current_hour + 1) % 24
            current_minute = 0
        
        # Get outdoor temperature for current hour
        outdoor_temp = outdoor_temps[current_hour]
        
        # Add slight randomness to outdoor temp
        outdoor_temp += random.uniform(-0.5, 0.5)
        
        # Update VAV based on current conditions
        vav.update(vav.zone_temp, supply_air_temp)
        
        # Calculate temperature effect
        vav_effect = 0
        if vav.mode == "cooling":
            vav_effect = vav.damper_position
        elif vav.mode == "heating" and vav.has_reheat:
            vav_effect = -vav.reheat_valve_position
        
        # Calculate temperature change
        temp_change = vav.calculate_thermal_behavior(
            minutes=15,  # 15-minute intervals
            outdoor_temp=outdoor_temp,
            vav_cooling_effect=vav_effect,
            time_of_day=(current_hour, current_minute)
        )
        
        # Update zone temperature
        vav.zone_temp += temp_change
        
        # Store data
        results['zone_temps'].append(vav.zone_temp)
        results['modes'].append(vav.mode)
        results['damper_positions'].append(vav.damper_position)
        results['reheat_positions'].append(vav.reheat_valve_position)
        results['hours'].append(current_hour)
        results['minutes'].append(current_minute)
        results['outdoor_temps'].append(outdoor_temp)
        
    return results

def plot_simulation_results(results, title):
    """Plot the simulation results."""
    # Calculate time in hours
    time_hours = [(results['hours'][i] + results['minutes'][i]/60) for i in range(len(results['hours']))]
    time_hours = [t - time_hours[0] + (24 if t < time_hours[0] else 0) for t in time_hours]
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    
    # Plot temperatures
    ax1.plot(time_hours, results['zone_temps'], 'b-', linewidth=2, label='Zone Temperature')
    ax1.plot(time_hours, results['outdoor_temps'], 'r--', linewidth=1, label='Outdoor Temperature')
    
    # Add setpoint reference lines
    vav_temp_setpoint = 72  # This should match the value used in simulations
    deadband = 2  # This should match the value used in simulations
    cooling_setpoint = vav_temp_setpoint + (deadband / 2)
    heating_setpoint = vav_temp_setpoint - (deadband / 2)
    
    ax1.axhline(y=cooling_setpoint, color='c', linestyle='-', alpha=0.5, label='Cooling Setpoint')
    ax1.axhline(y=heating_setpoint, color='orange', linestyle='-', alpha=0.5, label='Heating Setpoint')
    ax1.axhline(y=vav_temp_setpoint, color='g', linestyle='--', alpha=0.5, label='Temperature Setpoint')
    
    ax1.set_ylabel('Temperature (°F)')
    ax1.set_title(title)
    ax1.legend(loc='best')
    ax1.grid(True)
    
    # Plot control signals
    ax2.plot(time_hours, results['damper_positions'], 'b-', linewidth=2, label='Damper Position')
    ax2.plot(time_hours, results['reheat_positions'], 'r-', linewidth=2, label='Reheat Valve Position')
    
    # Create colormap for mode display
    mode_colors = {'cooling': 'blue', 'heating': 'red', 'deadband': 'green', 'initial': 'gray'}
    mode_values = [0.2 if mode == 'cooling' else 0.8 if mode == 'heating' else 0.5 for mode in results['modes']]
    
    ax2.plot(time_hours, mode_values, 'g--', linewidth=1, alpha=0.5, label='Mode')
    
    ax2.set_xlabel('Time (hours)')
    ax2.set_ylabel('Position (0-1)')
    ax2.set_ylim(-0.1, 1.1)
    ax2.legend(loc='best')
    ax2.grid(True)
    
    # Adjust layout and save
    plt.tight_layout()
    clean_title = title.replace(' ', '_').lower()
    plt.savefig(f"vav_convergence_{clean_title}.png")
    plt.close()

def main():
    """Run and plot various convergence simulations."""
    # Test Cooling Convergence
    vav = VAVBox(
        name="TestVAV",
        min_airflow=100,
        max_airflow=1000,
        zone_temp_setpoint=72,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=400,
        zone_volume=3200,
        window_area=80,
        window_orientation="east",
        thermal_mass=2.0,
    )
    
    # Set initial conditions - hot room
    vav.zone_temp = 78  # Above cooling setpoint (72 + 1 = 73)
    supply_air_temp = 55  # Cold supply air
    
    # Define simulation parameters
    outdoor_temps = {hour: 85 for hour in range(24)}  # Hot outside
    iterations = 3000
    
    # Run cooling simulation
    cooling_results = run_simulation(vav, supply_air_temp, outdoor_temps, iterations)
    plot_simulation_results(cooling_results, "Cooling Convergence Test")
    
    # Test Heating Convergence
    vav = VAVBox(
        name="TestVAV",
        min_airflow=100,
        max_airflow=1000,
        zone_temp_setpoint=72,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=400,
        zone_volume=3200,
        window_area=80,
        window_orientation="east",
        thermal_mass=2.0,
    )
    
    # Set initial conditions - cold room
    vav.zone_temp = 65  # Below heating setpoint (72 - 1 = 71)
    supply_air_temp = 55  # Cold supply air
    
    # Define simulation parameters
    outdoor_temps = {hour: 30 for hour in range(24)}  # Cold outside
    iterations = 3000
    
    # Run heating simulation
    heating_results = run_simulation(vav, supply_air_temp, outdoor_temps, iterations)
    plot_simulation_results(heating_results, "Heating Convergence Test")
    
    # Test with cycling outdoor temperatures
    vav = VAVBox(
        name="TestVAV",
        min_airflow=100,
        max_airflow=1000,
        zone_temp_setpoint=72,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=400,
        zone_volume=3200,
        window_area=80,
        window_orientation="east",
        thermal_mass=2.0,
    )
    
    # Set initial conditions - normal room
    vav.zone_temp = 72  # At setpoint
    supply_air_temp = 55  
    
    # Define simulation parameters - oscillating outdoor temperatures
    outdoor_temps = {
        hour: 60 + 20 * math.sin(math.pi * hour / 12) for hour in range(24)
    }  # 40°F to 80°F cycle
    iterations = 3000
    
    # Run cycling outdoor temps simulation
    cycling_results = run_simulation(vav, supply_air_temp, outdoor_temps, iterations)
    plot_simulation_results(cycling_results, "Cycling Outdoor Temperatures Test")
    
    # Test extreme conditions
    # Extreme cold
    vav = VAVBox(
        name="TestVAV",
        min_airflow=100,
        max_airflow=1000,
        zone_temp_setpoint=72,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=400,
        zone_volume=3200,
        window_area=80,
        window_orientation="east",
        thermal_mass=2.0,
    )
    
    vav.zone_temp = 72
    outdoor_temps_cold = {hour: -10 for hour in range(24)}  # Very cold outside
    extreme_cold_results = run_simulation(vav, 55, outdoor_temps_cold, 3000)
    plot_simulation_results(extreme_cold_results, "Extreme Cold Test")
    
    # Extreme heat
    vav = VAVBox(
        name="TestVAV",
        min_airflow=100,
        max_airflow=1000,
        zone_temp_setpoint=72,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=400,
        zone_volume=3200,
        window_area=80,
        window_orientation="east",
        thermal_mass=2.0,
    )
    
    vav.zone_temp = 72
    outdoor_temps_hot = {hour: 110 for hour in range(24)}  # Very hot outside
    extreme_hot_results = run_simulation(vav, 55, outdoor_temps_hot, 3000)
    plot_simulation_results(extreme_hot_results, "Extreme Heat Test")

if __name__ == "__main__":
    main()