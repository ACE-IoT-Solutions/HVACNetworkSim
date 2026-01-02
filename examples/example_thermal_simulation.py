#!/usr/bin/env python
"""
Example simulation demonstrating a single zone VAV box with occupancy and solar heat gain.
This simulates a zone's thermal behavior over a 24-hour period.
"""

import math
from src.vav_box import VAVBox
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import matplotlib.dates as mdates
from datetime import datetime, timedelta

def main():
    # Create two VAV boxes with different window orientations
    east_vav = VAVBox(
        name="East Office",
        min_airflow=200,  # CFM
        max_airflow=1500,  # CFM
        zone_temp_setpoint=72,  # °F
        deadband=2,  # °F
        discharge_air_temp_setpoint=55,  # °F
        has_reheat=True,
        zone_area=400,  # sq ft
        zone_volume=3200,  # cubic ft (8ft ceiling)
        window_area=100,  # sq ft
        window_orientation="east",
        thermal_mass=2.0  # Medium thermal mass
    )
    
    west_vav = VAVBox(
        name="West Office",
        min_airflow=200,  # CFM
        max_airflow=1500,  # CFM
        zone_temp_setpoint=72,  # °F
        deadband=2,  # °F
        discharge_air_temp_setpoint=55,  # °F
        has_reheat=True,
        zone_area=400,  # sq ft
        zone_volume=3200,  # cubic ft (8ft ceiling)
        window_area=100,  # sq ft
        window_orientation="west",
        thermal_mass=2.0  # Medium thermal mass
    )
    
    # Define outdoor temperature profile (24 hours)
    outdoor_temps = {}
    for hour in range(24):
        # Daily temperature cycle: lowest at 5am, highest at 3pm
        outdoor_temps[hour] = 65 + 15 * math.sin(math.pi * (hour - 5) / 12)
    
    # Define occupancy schedule
    occupied_hours = [(8, 18)]  # 8 AM to 6 PM
    occupancy = 10  # 10 people during occupied hours
    
    # Run 24-hour simulation with 15-minute intervals
    print("Running 24-hour thermal simulation...")
    east_results = east_vav.simulate_thermal_behavior(
        hours=24,
        interval_minutes=15,
        start_hour=0,  # Start at midnight
        outdoor_temps=outdoor_temps,
        occupied_hours=occupied_hours,
        occupancy=occupancy,
        supply_air_temp=55
    )
    
    west_results = west_vav.simulate_thermal_behavior(
        hours=24,
        interval_minutes=15,
        start_hour=0,  # Start at midnight
        outdoor_temps=outdoor_temps,
        occupied_hours=occupied_hours,
        occupancy=occupancy,
        supply_air_temp=55
    )
    
    # Plot results
    plot_results(east_results, west_results, outdoor_temps, occupied_hours)
    
    # Print summary statistics
    print_summary(east_results, "East Office")
    print_summary(west_results, "West Office")

def plot_results(east_results, west_results, outdoor_temps, occupied_hours):
    """Plot simulation results for both zones."""
    # Convert time tuples to datetime objects for better plotting
    base_date = datetime(2023, 6, 21)  # Summer solstice for maximum solar effect
    east_times = [base_date + timedelta(hours=h, minutes=m) for h, m in east_results['times']]
    
    # Create figure
    fig, axs = plt.subplots(4, 1, figsize=(12, 16), sharex=True)
    
    # Plot 1: Zone Temperatures
    ax1 = axs[0]
    ax1.plot(east_times, east_results['zone_temps'], 'r-', label='East Office Temp')
    ax1.plot(east_times, west_results['zone_temps'], 'b-', label='West Office Temp')
    
    # Add outdoor temperature
    outdoor_times = [base_date + timedelta(hours=h) for h in range(24)]
    outdoor_temp_values = [outdoor_temps[h] for h in range(24)]
    ax1.plot(outdoor_times, outdoor_temp_values, 'k--', label='Outdoor Temp')
    
    # Add setpoint reference
    ax1.axhline(y=72, color='g', linestyle=':', label='Setpoint (72°F)')
    ax1.axhline(y=73, color='g', linestyle='-.', alpha=0.5, label='Cooling Setpoint (73°F)')
    ax1.axhline(y=71, color='g', linestyle='-.', alpha=0.5, label='Heating Setpoint (71°F)')
    
    # Shade occupied hours
    for start, end in occupied_hours:
        start_time = base_date + timedelta(hours=start)
        end_time = base_date + timedelta(hours=end)
        ax1.axvspan(start_time, end_time, alpha=0.2, color='gray', label='_Occupied' if start == occupied_hours[0][0] else None)
    
    ax1.set_ylabel('Temperature (°F)')
    ax1.set_title('Zone Temperatures')
    ax1.legend()
    ax1.grid(True)
    
    # Plot 2: VAV Airflows
    ax2 = axs[1]
    ax2.plot(east_times, east_results['vav_airflows'], 'r-', label='East Office Airflow')
    ax2.plot(east_times, west_results['vav_airflows'], 'b-', label='West Office Airflow')
    ax2.set_ylabel('Airflow (CFM)')
    ax2.set_title('VAV Airflows')
    ax2.legend()
    ax2.grid(True)
    
    # Plot 3: Solar Heat Gain
    ax3 = axs[2]
    ax3.plot(east_times, east_results['solar_gains'], 'r-', label='East Office Solar Gain')
    ax3.plot(east_times, west_results['solar_gains'], 'b-', label='West Office Solar Gain')
    ax3.set_ylabel('Solar Gain (BTU/hr)')
    ax3.set_title('Solar Heat Gain')
    ax3.legend()
    ax3.grid(True)
    
    # Plot 4: VAV Modes
    ax4 = axs[3]
    
    # Convert modes to numeric values for plotting
    mode_values = {'cooling': 1, 'deadband': 0, 'heating': -1}
    east_mode_values = [mode_values[mode] for mode in east_results['vav_modes']]
    west_mode_values = [mode_values[mode] for mode in west_results['vav_modes']]
    
    ax4.plot(east_times, east_mode_values, 'r-', label='East Office')
    ax4.plot(east_times, west_mode_values, 'b-', label='West Office')
    ax4.set_yticks([-1, 0, 1])
    ax4.set_yticklabels(['Heating', 'Deadband', 'Cooling'])
    ax4.set_xlabel('Time of Day')
    ax4.set_title('VAV Operating Modes')
    ax4.legend()
    ax4.grid(True)
    
    # Format x-axis to show hours
    date_format = DateFormatter('%H:%M')
    for ax in axs:
        ax.xaxis.set_major_formatter(date_format)
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    
    plt.tight_layout()
    plt.savefig('thermal_simulation_results.png')
    print("Simulation results saved to thermal_simulation_results.png")

def print_summary(results, zone_name):
    """Print summary statistics for the simulation."""
    zone_temps = results['zone_temps']
    min_temp = min(zone_temps)
    max_temp = max(zone_temps)
    avg_temp = sum(zone_temps) / len(zone_temps)
    
    cooling_hours = sum(1 for mode in results['vav_modes'] if mode == 'cooling') * 15 / 60
    heating_hours = sum(1 for mode in results['vav_modes'] if mode == 'heating') * 15 / 60
    
    print(f"\n{zone_name} Summary:")
    print(f"  Temperature Range: {min_temp:.1f}°F to {max_temp:.1f}°F (Avg: {avg_temp:.1f}°F)")
    print(f"  Hours in Cooling Mode: {cooling_hours:.1f}")
    print(f"  Hours in Heating Mode: {heating_hours:.1f}")
    print(f"  Hours in Deadband: {24 - cooling_hours - heating_hours:.1f}")
    
    # Calculate average airflow during occupied hours
    occupied_airflows = []
    for i, (hour, minute) in enumerate(results['times']):
        if any(start <= hour < end for start, end in [(8, 18)]):  # 8am-6pm
            occupied_airflows.append(results['vav_airflows'][i])
    
    if occupied_airflows:
        avg_occupied_airflow = sum(occupied_airflows) / len(occupied_airflows)
        print(f"  Average Occupied Airflow: {avg_occupied_airflow:.0f} CFM")

if __name__ == "__main__":
    main()