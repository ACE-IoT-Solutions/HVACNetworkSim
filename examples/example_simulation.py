#!/usr/bin/env python
"""
Example simulation demonstrating the VAV box model.
This simulates a single zone VAV box over a 24-hour period.
"""

from src.vav_box import VAVBox
import matplotlib.pyplot as plt
import numpy as np

def main():
    # Create a VAV box
    vav = VAVBox(
        name="Office Zone",
        min_airflow=200,  # CFM
        max_airflow=1500,  # CFM
        zone_temp_setpoint=72,  # °F
        deadband=2,  # °F
        discharge_air_temp_setpoint=55,  # °F
        has_reheat=True
    )
    
    # Simulate 24 hours with 15-minute intervals (96 time steps)
    time_steps = 96
    hours = np.linspace(0, 24, time_steps)
    
    # Arrays to store simulation results
    zone_temps = []
    supply_air_temps = []
    discharge_air_temps = []
    airflows = []
    damper_positions = []
    reheat_positions = []
    cooling_energy = []
    heating_energy = []
    modes = []
    
    # Simulate a typical daily temperature profile (sinusoidal pattern)
    # Base load with occupancy and solar effects
    base_temp = 68  # Base temperature
    daily_amplitude = 8  # Daily swing
    occupancy_effect = 2  # Occupancy causes temperature rise
    
    supply_air_temp = 55  # Constant supply air temperature
    
    print("Running simulation...")
    for hour in hours:
        # Calculate zone temperature based on time of day
        # Simulate daily temperature swing with peak at 3 PM (hour 15)
        temp_sine = base_temp + daily_amplitude * np.sin((hour - 3) * np.pi / 12)
        
        # Add occupancy effect (8 AM to 6 PM)
        occupancy = 0
        if 8 <= hour <= 18:
            occupancy = occupancy_effect
        
        zone_temp = temp_sine + occupancy
        
        # Update VAV box
        vav.update(zone_temp, supply_air_temp)
        
        # Store results
        zone_temps.append(zone_temp)
        supply_air_temps.append(supply_air_temp)
        discharge_air_temps.append(vav.get_discharge_air_temp())
        airflows.append(vav.current_airflow)
        damper_positions.append(vav.damper_position * 100)  # Convert to percentage
        reheat_positions.append(vav.reheat_valve_position * 100)  # Convert to percentage
        
        energy_usage = vav.calculate_energy_usage()
        cooling_energy.append(energy_usage["cooling"])
        heating_energy.append(energy_usage["heating"])
        modes.append(vav.mode)
        
        # Print status at whole hours
        if hour % 1 == 0:
            print(f"Hour {int(hour)}: Zone Temp: {zone_temp:.1f}°F, Mode: {vav.mode}, "
                  f"Airflow: {vav.current_airflow:.0f} CFM, "
                  f"Discharge Temp: {vav.get_discharge_air_temp():.1f}°F")
    
    # Plot results
    try:
        plot_results(hours, zone_temps, supply_air_temps, discharge_air_temps, 
                    airflows, damper_positions, reheat_positions, 
                    cooling_energy, heating_energy, modes)
    except Exception as e:
        print(f"Unable to generate plot: {e}")
        print("Simulation complete.")

def plot_results(hours, zone_temps, supply_air_temps, discharge_air_temps, 
                airflows, damper_positions, reheat_positions, 
                cooling_energy, heating_energy, modes):
    """Generate plots of the simulation results."""
    plt.figure(figsize=(12, 16))
    
    # Plot 1: Temperatures
    plt.subplot(4, 1, 1)
    plt.plot(hours, zone_temps, 'r-', label='Zone Temp')
    plt.plot(hours, supply_air_temps, 'b-', label='Supply Air Temp')
    plt.plot(hours, discharge_air_temps, 'g-', label='Discharge Air Temp')
    plt.axhline(y=72, color='k', linestyle='--', label='Setpoint')
    plt.axhline(y=73, color='k', linestyle=':', alpha=0.5, label='Deadband')
    plt.axhline(y=71, color='k', linestyle=':', alpha=0.5)
    plt.xlabel('Hour of Day')
    plt.ylabel('Temperature (°F)')
    plt.title('Zone and Air Temperatures')
    plt.legend()
    plt.grid(True)
    
    # Plot 2: Airflow
    plt.subplot(4, 1, 2)
    plt.plot(hours, airflows, 'b-', label='Airflow (CFM)')
    plt.xlabel('Hour of Day')
    plt.ylabel('Airflow (CFM)')
    plt.title('VAV Airflow')
    plt.grid(True)
    
    # Plot 3: Control positions
    plt.subplot(4, 1, 3)
    plt.plot(hours, damper_positions, 'b-', label='Damper Position (%)')
    plt.plot(hours, reheat_positions, 'r-', label='Reheat Valve (%)')
    plt.xlabel('Hour of Day')
    plt.ylabel('Position (%)')
    plt.title('Damper and Reheat Valve Positions')
    plt.legend()
    plt.grid(True)
    
    # Plot 4: Energy
    plt.subplot(4, 1, 4)
    plt.plot(hours, cooling_energy, 'b-', label='Cooling Energy (BTU/hr)')
    plt.plot(hours, heating_energy, 'r-', label='Heating Energy (BTU/hr)')
    plt.xlabel('Hour of Day')
    plt.ylabel('Energy (BTU/hr)')
    plt.title('Energy Usage')
    plt.legend()
    plt.grid(True)
    
    # Mark operating modes on all plots
    mode_colors = {'cooling': 'lightblue', 'heating': 'salmon', 'deadband': 'lightgray'}
    mode_changes = []
    current_mode = modes[0]
    mode_changes.append((0, current_mode))
    
    for i in range(1, len(modes)):
        if modes[i] != current_mode:
            mode_changes.append((i, modes[i]))
            current_mode = modes[i]
    
    for ax in plt.gcf().get_axes():
        for i in range(len(mode_changes) - 1):
            start_idx = mode_changes[i][0]
            end_idx = mode_changes[i+1][0]
            mode = mode_changes[i][1]
            ax.axvspan(hours[start_idx], hours[end_idx], alpha=0.3, color=mode_colors.get(mode, 'white'))
        
        # Handle the last segment
        if mode_changes:
            start_idx = mode_changes[-1][0]
            mode = mode_changes[-1][1]
            ax.axvspan(hours[start_idx], hours[-1], alpha=0.3, color=mode_colors.get(mode, 'white'))
    
    plt.tight_layout()
    plt.savefig('vav_simulation_results.png')
    print("Simulation results saved to vav_simulation_results.png")

if __name__ == "__main__":
    main()