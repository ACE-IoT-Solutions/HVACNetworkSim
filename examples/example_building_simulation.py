#!/usr/bin/env python
"""
Example simulation demonstrating a complete building with multiple AHUs and zones.
This simulates a small office building over a 24-hour period.
"""

import math
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.building import Building

def main():
    """Run a whole-building simulation."""
    # Create the building
    building = Building(
        name="Small Office Building",
        location="Boston, MA",
        latitude=42.3601,
        longitude=-71.0589,
        floor_area=20000,  # sq ft
        num_floors=2,
        orientation=0,  # North-facing
        year_built=2010,
        timezone="America/New_York"
    )
    
    # Create VAV boxes for different zones - Floor 1
    floor1_office = VAVBox(
        name="Floor1_Office",
        min_airflow=300,
        max_airflow=2000,
        zone_temp_setpoint=72,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=6000,
        zone_volume=48000,
        window_area=800,
        window_orientation="south"
    )
    
    floor1_conference = VAVBox(
        name="Floor1_Conference",
        min_airflow=400,
        max_airflow=2500,
        zone_temp_setpoint=70,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=1500,
        zone_volume=12000,
        window_area=200,
        window_orientation="east"
    )
    
    floor1_lobby = VAVBox(
        name="Floor1_Lobby",
        min_airflow=500,
        max_airflow=3000,
        zone_temp_setpoint=74,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=False,
        zone_area=1000,
        zone_volume=8000,
        window_area=400,
        window_orientation="north"
    )
    
    # Create VAV boxes for different zones - Floor 2
    floor2_office = VAVBox(
        name="Floor2_Office",
        min_airflow=300,
        max_airflow=2000,
        zone_temp_setpoint=72,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=8000,
        zone_volume=64000,
        window_area=1000,
        window_orientation="south"
    )
    
    floor2_conference = VAVBox(
        name="Floor2_Conference",
        min_airflow=400,
        max_airflow=2500,
        zone_temp_setpoint=70,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=2000,
        zone_volume=16000,
        window_area=250,
        window_orientation="west"
    )
    
    # Add all zones to the building
    building.add_zone(floor1_office)
    building.add_zone(floor1_conference)
    building.add_zone(floor1_lobby)
    building.add_zone(floor2_office)
    building.add_zone(floor2_conference)
    
    # Create Air Handling Units
    ahu1 = AirHandlingUnit(
        name="AHU-1",
        cooling_type="chilled_water",
        supply_air_temp_setpoint=55,
        min_supply_air_temp=52,
        max_supply_air_temp=65,
        max_supply_airflow=7500,
        vav_boxes=[floor1_office, floor1_conference, floor1_lobby],
        enable_supply_temp_reset=True
    )
    
    ahu2 = AirHandlingUnit(
        name="AHU-2",
        cooling_type="dx",
        supply_air_temp_setpoint=55,
        min_supply_air_temp=52,
        max_supply_air_temp=65,
        max_supply_airflow=4500,
        vav_boxes=[floor2_office, floor2_conference],
        enable_supply_temp_reset=True,
        compressor_stages=3
    )
    
    # Add AHUs to the building
    building.add_air_handling_unit(ahu1)
    building.add_air_handling_unit(ahu2)
    
    # Generate weather data for a 24-hour period
    weather_data = generate_weather_data()
    
    # Set initial zone temperatures
    initial_temps = {
        "Floor1_Office": 72,
        "Floor1_Conference": 72,
        "Floor1_Lobby": 72,
        "Floor2_Office": 72,
        "Floor2_Conference": 72
    }
    
    # Run the simulation
    print("Running 24-hour building simulation...")
    results = building.run_simulation(
        weather_data=weather_data,
        interval_minutes=15,
        initial_zone_temps=initial_temps
    )
    
    # Generate energy report
    report = building.generate_energy_report(results)
    
    # Plot results
    plot_results(results, report)
    
    # Print summary
    print_summary(report)

def generate_weather_data():
    """Generate synthetic weather data for a 24-hour period."""
    weather_data = []
    
    # Start time (midnight)
    start_time = datetime(2023, 7, 15, 0, 0)
    
    # Generate data for each 15-minute interval (96 points)
    for i in range(96):
        # Current time
        current_time = start_time + timedelta(minutes=15 * i)
        hour = current_time.hour + current_time.minute / 60
        
        # Outdoor temperature model (lowest at 5am, highest at 3pm)
        temp = 65 + 20 * math.sin(math.pi * (hour - 5) / 12)
        
        # Humidity model (highest at night/morning, lowest in afternoon)
        humidity = 70 - 30 * math.sin(math.pi * (hour - 5) / 12)
        
        # Solar radiation (0 at night, peak at noon)
        if 6 <= hour <= 18:
            solar_factor = math.sin(math.pi * (hour - 6) / 12)
            solar_ghi = 1000 * solar_factor
        else:
            solar_ghi = 0
        
        # Create weather data point
        data_point = {
            "time": current_time,
            "temperature": temp,
            "humidity": humidity,
            "solar_ghi": solar_ghi,
            "wind_speed": 5 + 3 * math.sin(hour / 24 * 2 * math.pi),
            "wind_direction": (hour / 24 * 360) % 360  # Wind direction changes throughout the day
        }
        
        weather_data.append(data_point)
    
    return weather_data

def plot_results(results, report):
    """Plot building simulation results."""
    # Convert times to datetime objects for better plotting
    times = [result["time"] for result in results]
    
    # Extract data
    outdoor_temps = [result["outdoor_temp"] for result in results]
    
    # Zone temperatures
    zone_names = list(results[0]["zone_temps"].keys())
    zone_temps = {name: [result["zone_temps"][name] for result in results] for name in zone_names}
    
    # Energy data for each timestep
    cooling_energy = [result["energy"]["cooling"] / 1000 for result in results]  # Convert to kBTU/hr
    heating_energy = [result["energy"]["heating"] / 1000 for result in results]
    fan_energy = [result["energy"]["fan"] / 1000 for result in results]
    
    # Create figure
    fig, axs = plt.subplots(3, 1, figsize=(12, 14), sharex=True)
    
    # Plot 1: Temperatures
    ax1 = axs[0]
    ax1.plot(times, outdoor_temps, 'k-', label='Outdoor Temp')
    
    # Plot zone temperatures with different colors
    colors = ['r', 'g', 'b', 'm', 'c']
    for i, name in enumerate(zone_names):
        ax1.plot(times, zone_temps[name], f'{colors[i%len(colors)]}-', label=f'{name}')
    
    # Add setpoint reference
    ax1.axhline(y=72, color='gray', linestyle=':', label='Primary Setpoint (72°F)')
    
    ax1.set_ylabel('Temperature (°F)')
    ax1.set_title('Building Temperatures')
    ax1.legend(loc='upper left', fontsize=8)
    ax1.grid(True)
    
    # Format x-axis
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    
    # Plot 2: Energy Usage
    ax2 = axs[1]
    ax2.plot(times, cooling_energy, 'b-', label='Cooling Energy')
    ax2.plot(times, heating_energy, 'r-', label='Heating Energy')
    ax2.plot(times, fan_energy, 'g-', label='Fan Energy')
    
    # Total energy
    total_energy = [c + h + f for c, h, f in zip(cooling_energy, heating_energy, fan_energy)]
    ax2.plot(times, total_energy, 'k--', label='Total Energy')
    
    ax2.set_ylabel('Energy (kBTU/hr)')
    ax2.set_title('Building Energy Usage')
    ax2.legend(loc='upper left', fontsize=8)
    ax2.grid(True)
    
    # Plot 3: Energy by AHU
    ax3 = axs[2]
    
    # Create a stacked bar chart of energy by equipment
    ahu_names = list(report["energy_by_equipment"].keys())
    values = [report["energy_by_equipment"][name] / 1000 for name in ahu_names]  # kBTU
    
    # Use integer indices for x-axis to avoid matplotlib date conversion issues
    x_pos = list(range(len(ahu_names)))
    bars = ax3.bar(x_pos, values)
    
    # Set x tick labels
    ax3.set_xticks(x_pos)
    ax3.set_xticklabels(ahu_names)
    
    # Add percentage labels
    total = sum(values)
    for i, v in enumerate(values):
        ax3.text(i, v + 0.1, f"{v/total*100:.1f}%", ha='center', fontsize=9)
    
    ax3.set_xlabel('Equipment')
    ax3.set_ylabel('Energy (kBTU)')
    ax3.set_title('Total Energy by Equipment')
    ax3.grid(True, axis='y')
    
    plt.tight_layout()
    plt.savefig('building_simulation_results.png')
    print("Simulation results saved to building_simulation_results.png")

def print_summary(report):
    """Print energy report summary."""
    print("\nBuilding Energy Summary:")
    print(f"Total Energy: {report['total_energy']/1000:.1f} kBTU")
    print("\nEnergy by Type:")
    for energy_type, value in report["energy_by_type"].items():
        print(f"  {energy_type.capitalize()}: {value/1000:.1f} kBTU ({value/report['total_energy']*100:.1f}%)")
    
    print("\nEnergy by Equipment:")
    for equipment, value in report["energy_by_equipment"].items():
        print(f"  {equipment}: {value/1000:.1f} kBTU ({value/report['total_energy']*100:.1f}%)")
    
    print(f"\nPeak Demand: {report['peak_demand']/1000:.1f} kBTU/hr")

if __name__ == "__main__":
    main()