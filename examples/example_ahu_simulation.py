#!/usr/bin/env python
"""
Example simulation demonstrating an AHU controlling multiple VAV boxes.
This simulates a small building HVAC system over a 24-hour period.
"""

from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
import matplotlib.pyplot as plt
import numpy as np

def main():
    # Create VAV boxes for different zones
    vav_office = VAVBox(
        name="Office",
        min_airflow=200,  # CFM
        max_airflow=1500,  # CFM
        zone_temp_setpoint=72,  # °F
        deadband=2,  # °F
        discharge_air_temp_setpoint=55,  # °F
        has_reheat=True
    )
    
    vav_conference = VAVBox(
        name="Conference",
        min_airflow=300,  # CFM
        max_airflow=2000,  # CFM
        zone_temp_setpoint=70,  # °F
        deadband=2,  # °F
        discharge_air_temp_setpoint=55,  # °F
        has_reheat=True
    )
    
    vav_lobby = VAVBox(
        name="Lobby",
        min_airflow=400,  # CFM
        max_airflow=2500,  # CFM
        zone_temp_setpoint=74,  # °F
        deadband=2,  # °F
        discharge_air_temp_setpoint=55,  # °F
        has_reheat=False  # No reheat in the lobby
    )
    
    # Create the AHU
    ahu = AirHandlingUnit(
        name="AHU-1",
        supply_air_temp_setpoint=55,  # °F
        min_supply_air_temp=52,  # °F
        max_supply_air_temp=65,  # °F
        max_supply_airflow=6000,  # CFM
        vav_boxes=[vav_office, vav_conference, vav_lobby],
        enable_supply_temp_reset=True  # Enable supply temp reset for energy efficiency
    )
    
    # Simulate 24 hours with 15-minute intervals (96 time steps)
    time_steps = 96
    hours = np.linspace(0, 24, time_steps)
    
    # Arrays to store simulation results
    office_temps = []
    conference_temps = []
    lobby_temps = []
    supply_air_temps = []
    office_airflows = []
    conference_airflows = []
    lobby_airflows = []
    total_airflows = []
    cooling_valve = []
    heating_valve = []
    cooling_energy = []
    heating_energy = []
    fan_energy = []
    
    # Simulate outdoor temperature profile
    outdoor_temps = []
    for hour in hours:
        # Daily temperature cycle: lowest at 5am, highest at 3pm
        outdoor_temp = 65 + 15 * np.sin(np.pi * (hour - 5) / 12)
        outdoor_temps.append(outdoor_temp)
    
    # Set up zone temperature models
    # Define occupancy patterns
    office_occupancy = np.zeros(time_steps)
    conference_occupancy = np.zeros(time_steps)
    lobby_occupancy = np.zeros(time_steps)
    
    # Office: 8am to 6pm
    office_occupancy[(hours >= 8) & (hours <= 18)] = 1.0
    
    # Conference room: Meetings at 9am, 11am, 2pm, 4pm
    for meeting_hour in [9, 11, 14, 16]:
        idx = np.where((hours >= meeting_hour) & (hours <= meeting_hour + 1))[0]
        conference_occupancy[idx] = 2.0  # More people = more heat
    
    # Lobby: 7am to 7pm
    lobby_occupancy[(hours >= 7) & (hours <= 19)] = 0.8
    
    print("Running AHU simulation...")
    for i, hour in enumerate(hours):
        # Calculate zone temperatures based on previous conditions, outdoor temp, and occupancy
        # Start with baseline temperatures
        if i == 0:
            office_temp = 72
            conference_temp = 70
            lobby_temp = 74
        else:
            # Simple thermal model: zone temperature is affected by:
            # 1. Previous temperature (thermal mass)
            # 2. Outdoor temperature influence
            # 3. Occupancy heat gain
            # 4. Cooling/heating effect from VAV (from previous step)
            
            # Office zone
            outdoor_influence = 0.1 * (outdoor_temps[i-1] - office_temps[i-1])
            occupancy_gain = 2 * office_occupancy[i-1]
            vav_effect = -0.5 * (vav_office.current_airflow / vav_office.max_airflow) * (office_temps[i-1] - vav_office.get_discharge_air_temp())
            office_temp = office_temps[i-1] + outdoor_influence + occupancy_gain + vav_effect
            
            # Conference zone
            outdoor_influence = 0.08 * (outdoor_temps[i-1] - conference_temps[i-1])
            occupancy_gain = 3 * conference_occupancy[i-1]
            vav_effect = -0.7 * (vav_conference.current_airflow / vav_conference.max_airflow) * (conference_temps[i-1] - vav_conference.get_discharge_air_temp())
            conference_temp = conference_temps[i-1] + outdoor_influence + occupancy_gain + vav_effect
            
            # Lobby zone
            outdoor_influence = 0.15 * (outdoor_temps[i-1] - lobby_temps[i-1])  # More outdoor influence in lobby
            occupancy_gain = 1 * lobby_occupancy[i-1]
            vav_effect = -0.4 * (vav_lobby.current_airflow / vav_lobby.max_airflow) * (lobby_temps[i-1] - vav_lobby.get_discharge_air_temp())
            lobby_temp = lobby_temps[i-1] + outdoor_influence + occupancy_gain + vav_effect
        
        # Update AHU with current zone temperatures
        zone_temps = {
            "Office": office_temp,
            "Conference": conference_temp,
            "Lobby": lobby_temp
        }
        
        ahu.update(zone_temps, outdoor_temps[i])
        
        # Store results
        office_temps.append(office_temp)
        conference_temps.append(conference_temp)
        lobby_temps.append(lobby_temp)
        supply_air_temps.append(ahu.current_supply_air_temp)
        office_airflows.append(vav_office.current_airflow)
        conference_airflows.append(vav_conference.current_airflow)
        lobby_airflows.append(vav_lobby.current_airflow)
        total_airflows.append(ahu.current_total_airflow)
        cooling_valve.append(ahu.cooling_valve_position * 100)  # Convert to percentage
        heating_valve.append(ahu.heating_valve_position * 100)  # Convert to percentage
        
        energy = ahu.calculate_energy_usage()
        cooling_energy.append(energy["cooling"] / 1000)  # Convert to kBTU/hr
        heating_energy.append(energy["heating"] / 1000)  # Convert to kBTU/hr
        fan_energy.append(energy["fan"] / 1000)  # Convert to kBTU/hr
        
        # Print status at whole hours
        if hour % 3 == 0:
            print(f"Hour {int(hour)}: Outdoor Temp: {outdoor_temps[i]:.1f}°F")
            print(f"  Office: {office_temp:.1f}°F, Airflow: {vav_office.current_airflow:.0f} CFM")
            print(f"  Conference: {conference_temp:.1f}°F, Airflow: {vav_conference.current_airflow:.0f} CFM")
            print(f"  Lobby: {lobby_temp:.1f}°F, Airflow: {vav_lobby.current_airflow:.0f} CFM")
            print(f"  AHU: Supply Temp: {ahu.current_supply_air_temp:.1f}°F, Total Airflow: {ahu.current_total_airflow:.0f} CFM")
            print(f"  Valves: Cooling: {ahu.cooling_valve_position*100:.0f}%, Heating: {ahu.heating_valve_position*100:.0f}%")
            print()
    
    # Plot results
    try:
        plot_results(hours, outdoor_temps, office_temps, conference_temps, lobby_temps, 
                     supply_air_temps, office_airflows, conference_airflows, lobby_airflows,
                     total_airflows, cooling_valve, heating_valve, cooling_energy, 
                     heating_energy, fan_energy)
    except Exception as e:
        print(f"Unable to generate plot: {e}")
        print("Simulation complete.")

def plot_results(hours, outdoor_temps, office_temps, conference_temps, lobby_temps, 
                 supply_air_temps, office_airflows, conference_airflows, lobby_airflows,
                 total_airflows, cooling_valve, heating_valve, cooling_energy, 
                 heating_energy, fan_energy):
    """Generate plots of the simulation results."""
    plt.figure(figsize=(12, 20))
    
    # Plot 1: Temperatures
    plt.subplot(5, 1, 1)
    plt.plot(hours, outdoor_temps, 'k-', label='Outdoor Temp')
    plt.plot(hours, office_temps, 'r-', label='Office Temp')
    plt.plot(hours, conference_temps, 'g-', label='Conference Temp')
    plt.plot(hours, lobby_temps, 'b-', label='Lobby Temp')
    plt.plot(hours, supply_air_temps, 'c--', label='Supply Air Temp')
    plt.axhline(y=72, color='r', linestyle=':', alpha=0.5, label='Office Setpoint')
    plt.axhline(y=70, color='g', linestyle=':', alpha=0.5, label='Conference Setpoint')
    plt.axhline(y=74, color='b', linestyle=':', alpha=0.5, label='Lobby Setpoint')
    plt.xlabel('Hour of Day')
    plt.ylabel('Temperature (°F)')
    plt.title('Zone and Air Temperatures')
    plt.legend()
    plt.grid(True)
    
    # Plot 2: Individual VAV Airflows
    plt.subplot(5, 1, 2)
    plt.plot(hours, office_airflows, 'r-', label='Office Airflow')
    plt.plot(hours, conference_airflows, 'g-', label='Conference Airflow')
    plt.plot(hours, lobby_airflows, 'b-', label='Lobby Airflow')
    plt.xlabel('Hour of Day')
    plt.ylabel('Airflow (CFM)')
    plt.title('VAV Airflows')
    plt.legend()
    plt.grid(True)
    
    # Plot 3: Total Airflow
    plt.subplot(5, 1, 3)
    plt.plot(hours, total_airflows, 'k-', label='Total Airflow (CFM)')
    plt.xlabel('Hour of Day')
    plt.ylabel('Airflow (CFM)')
    plt.title('Total System Airflow')
    plt.grid(True)
    
    # Plot 4: Valve Positions
    plt.subplot(5, 1, 4)
    plt.plot(hours, cooling_valve, 'b-', label='Cooling Valve (%)')
    plt.plot(hours, heating_valve, 'r-', label='Heating Valve (%)')
    plt.xlabel('Hour of Day')
    plt.ylabel('Valve Position (%)')
    plt.title('AHU Valve Positions')
    plt.legend()
    plt.grid(True)
    
    # Plot 5: Energy Usage
    plt.subplot(5, 1, 5)
    plt.plot(hours, cooling_energy, 'b-', label='Cooling Energy (kBTU/hr)')
    plt.plot(hours, heating_energy, 'r-', label='Heating Energy (kBTU/hr)')
    plt.plot(hours, fan_energy, 'g-', label='Fan Energy (kBTU/hr)')
    plt.plot(hours, [c+h+f for c,h,f in zip(cooling_energy, heating_energy, fan_energy)], 'k--', label='Total Energy (kBTU/hr)')
    plt.xlabel('Hour of Day')
    plt.ylabel('Energy (kBTU/hr)')
    plt.title('Energy Usage')
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig('ahu_simulation_results.png')
    print("Simulation results saved to ahu_simulation_results.png")

if __name__ == "__main__":
    main()