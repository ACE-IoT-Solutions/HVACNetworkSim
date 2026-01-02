#!/usr/bin/env python
"""
Example simulation demonstrating a complete HVAC system with all component types.
This simulates a mixed-use building with multiple HVAC systems over a 24-hour period.
"""

import math
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.cooling_tower import CoolingTower
from src.chiller import Chiller
from src.boiler import Boiler
from src.building import Building

def main():
    """Run a complete building HVAC system simulation."""
    # Create the building
    building = Building(
        name="Mixed-Use Building",
        location="Chicago, IL",
        latitude=41.8781,
        longitude=-87.6298,
        floor_area=100000,  # sq ft
        num_floors=4,
        orientation=0,  # North-facing
        year_built=2010,
        timezone="America/Chicago"
    )
    
    # Create cooling towers
    cooling_tower1 = CoolingTower(
        name="CT-1",
        capacity=800,  # tons
        design_approach=5,  # °F
        design_range=10,  # °F
        design_wet_bulb=78,  # °F
        min_speed=20,  # %
        tower_type="counterflow",
        fan_power=60,  # kW
        num_cells=3
    )
    
    cooling_tower2 = CoolingTower(
        name="CT-2",
        capacity=400,  # tons
        design_approach=5,  # °F
        design_range=10,  # °F
        design_wet_bulb=78,  # °F
        min_speed=20,  # %
        tower_type="crossflow",
        fan_power=35,  # kW
        num_cells=2
    )
    
    # Create chillers
    water_cooled_chiller = Chiller(
        name="Chiller-1",
        cooling_type="water_cooled",
        capacity=750,  # tons
        design_cop=6.0,
        design_entering_condenser_temp=85,  # °F
        design_leaving_chilled_water_temp=44,  # °F
        min_part_load_ratio=0.1,
        design_chilled_water_flow=1800,  # GPM
        design_condenser_water_flow=2250  # GPM
    )
    
    air_cooled_chiller = Chiller(
        name="Chiller-2",
        cooling_type="air_cooled",
        capacity=400,  # tons
        design_cop=3.2,
        design_entering_condenser_temp=95,  # °F
        design_leaving_chilled_water_temp=44,  # °F
        min_part_load_ratio=0.15,
        design_chilled_water_flow=960  # GPM
    )
    
    # Create boilers
    gas_boiler = Boiler(
        name="Boiler-1",
        fuel_type="gas",
        capacity=5000,  # MBH
        design_efficiency=0.92,
        design_entering_water_temp=160,  # °F
        design_leaving_water_temp=180,  # °F
        min_part_load_ratio=0.2,
        design_hot_water_flow=500,  # GPM
        condensing=True,
        turndown_ratio=5.0
    )
    
    electric_boiler = Boiler(
        name="Boiler-2",
        fuel_type="electric",
        capacity=2000,  # MBH
        design_efficiency=0.99,
        design_entering_water_temp=160,  # °F
        design_leaving_water_temp=180,  # °F
        min_part_load_ratio=0.1,
        design_hot_water_flow=200,  # GPM
        condensing=False,
        turndown_ratio=10.0
    )
    
    # Connect chillers to cooling towers
    water_cooled_chiller.connect_cooling_tower(cooling_tower1)
    
    # ---------- Create VAVs and AHUs ----------
    
    # North Zone VAVs - Office Area - Served by AHU-1 (Water-cooled chiller-based)
    north_vavs = []
    
    for i in range(1, 6):
        vav = VAVBox(
            name=f"North_VAV{i}",
            min_airflow=200,
            max_airflow=1500,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=800,
            zone_volume=9600,
            window_area=120,
            window_orientation="north"
        )
        north_vavs.append(vav)
        building.add_zone(vav)
    
    # South Zone VAVs - Retail Area - Served by AHU-2 (Air-cooled chiller-based)
    south_vavs = []
    
    for i in range(1, 4):
        vav = VAVBox(
            name=f"South_VAV{i}",
            min_airflow=300,
            max_airflow=2000,
            zone_temp_setpoint=74,  # Higher setpoint for retail
            deadband=2,
            discharge_air_temp_setpoint=58,
            has_reheat=True,
            zone_area=1200,
            zone_volume=14400,
            window_area=200,
            window_orientation="south"
        )
        south_vavs.append(vav)
        building.add_zone(vav)
    
    # East Zone VAVs - Conference Areas - Served by AHU-3 (Water-cooled chiller-based)
    east_vavs = []
    
    for i in range(1, 3):
        vav = VAVBox(
            name=f"East_VAV{i}",
            min_airflow=400,
            max_airflow=3000,
            zone_temp_setpoint=70,  # Lower setpoint for conference rooms
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=900,
            zone_volume=10800,
            window_area=150,
            window_orientation="east"
        )
        east_vavs.append(vav)
        building.add_zone(vav)
    
    # West Zone VAVs - Lobby/Common Areas - Mix of reheat and no reheat
    west_vavs = []
    
    west_vav1 = VAVBox(
        name="West_VAV1",
        min_airflow=500,
        max_airflow=4000,
        zone_temp_setpoint=73,
        deadband=2,
        discharge_air_temp_setpoint=58,
        has_reheat=False,  # No reheat for lobby
        zone_area=1800,
        zone_volume=25200,
        window_area=350,
        window_orientation="west"
    )
    
    west_vav2 = VAVBox(
        name="West_VAV2",
        min_airflow=200,
        max_airflow=1200,
        zone_temp_setpoint=72,
        deadband=2,
        discharge_air_temp_setpoint=55,
        has_reheat=True,
        zone_area=600,
        zone_volume=7200,
        window_area=100,
        window_orientation="west"
    )
    
    west_vavs = [west_vav1, west_vav2]
    building.add_zone(west_vav1)
    building.add_zone(west_vav2)
    
    # Create AHUs
    ahu1 = AirHandlingUnit(
        name="AHU-1-North",
        cooling_type="chilled_water",
        supply_air_temp_setpoint=55,
        min_supply_air_temp=52,
        max_supply_air_temp=65,
        max_supply_airflow=7500,
        vav_boxes=north_vavs,
        enable_supply_temp_reset=True
    )
    
    ahu2 = AirHandlingUnit(
        name="AHU-2-South",
        cooling_type="dx",
        supply_air_temp_setpoint=58,
        min_supply_air_temp=55,
        max_supply_air_temp=65,
        max_supply_airflow=6000,
        vav_boxes=south_vavs,
        enable_supply_temp_reset=True,
        compressor_stages=3
    )
    
    ahu3 = AirHandlingUnit(
        name="AHU-3-East",
        cooling_type="chilled_water",
        supply_air_temp_setpoint=55,
        min_supply_air_temp=52,
        max_supply_air_temp=65,
        max_supply_airflow=6000,
        vav_boxes=east_vavs,
        enable_supply_temp_reset=True
    )
    
    ahu4 = AirHandlingUnit(
        name="AHU-4-West",
        cooling_type="chilled_water",
        supply_air_temp_setpoint=58,
        min_supply_air_temp=55,
        max_supply_air_temp=65,
        max_supply_airflow=5200,
        vav_boxes=west_vavs,
        enable_supply_temp_reset=True
    )
    
    # Add AHUs to building
    building.add_air_handling_unit(ahu1)
    building.add_air_handling_unit(ahu2)
    building.add_air_handling_unit(ahu3)
    building.add_air_handling_unit(ahu4)
    
    # Generate weather data for a 24-hour period
    weather_data = generate_weather_data()
    
    # Set initial zone temperatures
    initial_temps = {}
    for vav in north_vavs + south_vavs + east_vavs + west_vavs:
        initial_temps[vav.name] = 72  # Start all zones at 72°F
    
    # Run the simulation
    print("Running 24-hour complete system simulation...")
    
    # Set up equipment performance tracking
    chiller_loads = {
        "water_cooled": [],
        "air_cooled": []
    }
    chiller_cops = {
        "water_cooled": [],
        "air_cooled": []
    }
    tower_approaches = []
    boiler_loads = {
        "gas": [],
        "electric": []
    }
    boiler_efficiencies = {
        "gas": [],
        "electric": []
    }
    timestamp_hours = []
    outdoor_temps = []
    
    # Simulation time step in minutes
    time_step = 60  # 1 hour time step for simplicity
    simulation_hours = 24
    
    # Start simulation at midnight
    simulation_time = datetime(2023, 1, 15, 0, 0)
    building.set_time(simulation_time)
    
    # Initialize lists to store results
    zone_temps_by_type = {
        "north": [],
        "south": [],
        "east": [],
        "west": []
    }
    
    ahu_airflows = {
        "AHU-1-North": [],
        "AHU-2-South": [],
        "AHU-3-East": [],
        "AHU-4-West": []
    }
    
    cooling_energy = []
    heating_energy = []
    fan_energy = []
    total_energy = []
    
    # Run simulation
    for hour in range(simulation_hours):
        current_outdoor_temp = weather_data[hour]["temperature"]
        current_wet_bulb = estimate_wet_bulb(current_outdoor_temp, weather_data[hour]["humidity"])
        
        # Update timestamp
        timestamp_hours.append(hour)
        outdoor_temps.append(current_outdoor_temp)
        
        # Set outdoor conditions
        building.set_outdoor_conditions(
            temperature=current_outdoor_temp,
            humidity=weather_data[hour]["humidity"],
            wind_speed=weather_data[hour]["wind_speed"],
            wind_direction=weather_data[hour]["wind_direction"],
            solar_ghi=weather_data[hour]["solar_ghi"]
        )
        
        # Update zone temperatures based on previous control actions, occupancy, etc.
        # In real simulation this would be more complex with thermal modeling
        updated_zone_temps = simulate_zone_temperatures(
            building.zones,
            current_outdoor_temp,
            hour,
            building.solar_ghi
        )
        
        # Update building with new zone temperatures
        building.set_zone_temperatures(updated_zone_temps)
        
        # Update AHUs based on zone requirements
        building.update_equipment()
        
        # Update cooling plant based on AHU loads
        chilled_water_load = calculate_chw_load(ahu1, ahu3, ahu4)  # CHW AHUs
        dx_cooling_load = calculate_dx_load(ahu2)  # DX AHU
        
        # Calculate hot water load for boilers
        hot_water_load = calculate_hw_load(north_vavs, south_vavs, east_vavs, west_vavs)
        
        # Split load between gas and electric boilers (70/30 split)
        gas_boiler_load = hot_water_load * 0.7
        electric_boiler_load = hot_water_load * 0.3
        
        # Update chillers
        water_cooled_chiller.update_load(
            load=chilled_water_load * 0.8,  # 80% of CHW load to water-cooled
            entering_chilled_water_temp=54,
            chilled_water_flow=1800,
            ambient_wet_bulb=current_wet_bulb,
            ambient_dry_bulb=current_outdoor_temp
        )
        
        air_cooled_chiller.update_load(
            load=chilled_water_load * 0.2 + dx_cooling_load,  # 20% of CHW load plus DX load
            entering_chilled_water_temp=54,
            chilled_water_flow=960,
            ambient_wet_bulb=current_wet_bulb,
            ambient_dry_bulb=current_outdoor_temp
        )
        
        # Update boilers
        gas_boiler.update_load(
            load=gas_boiler_load,
            entering_water_temp=160,
            hot_water_flow=500,
            ambient_temp=75
        )
        
        electric_boiler.update_load(
            load=electric_boiler_load,
            entering_water_temp=160,
            hot_water_flow=200,
            ambient_temp=75
        )
        
        # Track equipment performance
        chiller_loads["water_cooled"].append(water_cooled_chiller.current_load)
        chiller_loads["air_cooled"].append(air_cooled_chiller.current_load)
        chiller_cops["water_cooled"].append(water_cooled_chiller.current_cop)
        chiller_cops["air_cooled"].append(air_cooled_chiller.current_cop)
        
        if water_cooled_chiller.cooling_tower is not None:
            tower_approaches.append(water_cooled_chiller.cooling_tower.calculate_approach())
        
        boiler_loads["gas"].append(gas_boiler.current_load)
        boiler_loads["electric"].append(electric_boiler.current_load)
        boiler_efficiencies["gas"].append(gas_boiler.current_efficiency)
        boiler_efficiencies["electric"].append(electric_boiler.current_efficiency)
        
        # Track zone temperatures by type
        north_avg_temp = sum(updated_zone_temps[vav.name] for vav in north_vavs) / len(north_vavs)
        south_avg_temp = sum(updated_zone_temps[vav.name] for vav in south_vavs) / len(south_vavs)
        east_avg_temp = sum(updated_zone_temps[vav.name] for vav in east_vavs) / len(east_vavs)
        west_avg_temp = sum(updated_zone_temps[vav.name] for vav in west_vavs) / len(west_vavs)
        
        zone_temps_by_type["north"].append(north_avg_temp)
        zone_temps_by_type["south"].append(south_avg_temp)
        zone_temps_by_type["east"].append(east_avg_temp)
        zone_temps_by_type["west"].append(west_avg_temp)
        
        # Track AHU airflows
        ahu_airflows["AHU-1-North"].append(ahu1.current_total_airflow)
        ahu_airflows["AHU-2-South"].append(ahu2.current_total_airflow)
        ahu_airflows["AHU-3-East"].append(ahu3.current_total_airflow)
        ahu_airflows["AHU-4-West"].append(ahu4.current_total_airflow)
        
        # Calculate energy usage
        total_cooling = water_cooled_chiller.calculate_power_consumption() + air_cooled_chiller.calculate_power_consumption()
        total_cooling += cooling_tower1.calculate_power_consumption()  # Add tower fan power
        
        total_heating = 0
        if electric_boiler.fuel_type == "electric":
            electric_consumption = electric_boiler.calculate_fuel_consumption()
            total_heating += electric_consumption.get("kilowatt_hours", 0)
        
        total_fan = sum(ahu.calculate_fan_power() for ahu in [ahu1, ahu2, ahu3, ahu4])
        
        cooling_energy.append(total_cooling)
        heating_energy.append(total_heating)
        fan_energy.append(total_fan)
        total_energy.append(total_cooling + total_heating + total_fan)
        
        # Advance simulation time
        simulation_time += timedelta(minutes=time_step)
        building.set_time(simulation_time)
        
        # Status printout every 6 hours
        if hour % 6 == 0:
            print(f"Hour {hour}: Outdoor Temp: {current_outdoor_temp:.1f}°F, WB: {current_wet_bulb:.1f}°F")
            print(f"  Water-Cooled Chiller: {water_cooled_chiller.current_load:.0f} tons, COP: {water_cooled_chiller.current_cop:.2f}")
            print(f"  Air-Cooled Chiller: {air_cooled_chiller.current_load:.0f} tons, COP: {air_cooled_chiller.current_cop:.2f}")
            print(f"  Cooling Tower Approach: {water_cooled_chiller.cooling_tower.calculate_approach():.1f}°F")
            print(f"  Gas Boiler: {gas_boiler.current_load:.0f} MBH, Efficiency: {gas_boiler.current_efficiency*100:.1f}%")
            print(f"  Electric Boiler: {electric_boiler.current_load:.0f} MBH")
            print(f"  Total Power: {total_energy[-1]:.1f} kW")
            print()
    
    # Create a summary of energy usage
    # Convert kW to kWh by assuming uniform consumption during the hour
    cooling_kwh = sum(cooling_energy)
    heating_kwh = sum(heating_energy)
    fan_kwh = sum(fan_energy)
    total_kwh = sum(total_energy)
    
    # Gas consumption in therms
    gas_consumption = sum(gas_boiler.calculate_fuel_consumption()["therms_per_hour"] for _ in range(len(timestamp_hours)))
    
    # Plot results
    print("\nCreating visualization of results...")
    plot_results(
        timestamp_hours, 
        outdoor_temps,
        zone_temps_by_type,
        chiller_loads,
        chiller_cops,
        tower_approaches,
        boiler_loads,
        boiler_efficiencies,
        ahu_airflows,
        cooling_energy,
        heating_energy,
        fan_energy
    )
    
    # Print summary
    print("\nSimulation Summary")
    print("=================")
    print(f"Total Electricity Usage: {total_kwh:.1f} kWh")
    print(f"  Cooling: {cooling_kwh:.1f} kWh ({cooling_kwh/total_kwh*100:.1f}%)")
    print(f"  Heating (Electric): {heating_kwh:.1f} kWh ({heating_kwh/total_kwh*100:.1f}%)")
    print(f"  Fans: {fan_kwh:.1f} kWh ({fan_kwh/total_kwh*100:.1f}%)")
    print(f"Gas Usage: {gas_consumption:.1f} therms")
    print(f"Average Water-Cooled Chiller COP: {sum(chiller_cops['water_cooled'])/len(chiller_cops['water_cooled']):.2f}")
    print(f"Average Air-Cooled Chiller COP: {sum(chiller_cops['air_cooled'])/len(chiller_cops['air_cooled']):.2f}")
    print(f"Average Gas Boiler Efficiency: {sum(boiler_efficiencies['gas'])/len(boiler_efficiencies['gas'])*100:.1f}%")

def generate_weather_data():
    """Generate synthetic weather data for a 24-hour period."""
    weather_data = []
    
    # Generate data for each hour
    for hour in range(24):
        # Outdoor temperature model (lowest at 5am, highest at 3pm)
        temp = 35 + 25 * math.sin(math.pi * (hour - 5) / 12)  # Range from 35°F to 60°F (winter day)
        
        # Humidity model (highest at night/morning, lowest in afternoon)
        humidity = 65 - 20 * math.sin(math.pi * (hour - 5) / 12)
        
        # Solar radiation (0 at night, peak at noon)
        if 7 <= hour <= 17:  # Winter daylight hours
            solar_factor = math.sin(math.pi * (hour - 7) / 10)
            solar_ghi = 600 * solar_factor  # Winter solar radiation peak ~600 W/m²
        else:
            solar_ghi = 0
        
        # Wind speed and direction
        wind_speed = 5 + 5 * math.sin(hour / 12 * math.pi)
        wind_direction = (hour * 15) % 360
        
        # Create weather data point
        data_point = {
            "hour": hour,
            "temperature": temp,
            "humidity": humidity,
            "solar_ghi": solar_ghi,
            "wind_speed": wind_speed,
            "wind_direction": wind_direction
        }
        
        weather_data.append(data_point)
    
    return weather_data

def estimate_wet_bulb(dry_bulb, relative_humidity):
    """Estimate wet bulb temperature from dry bulb and relative humidity."""
    # Simplified equation for wet bulb calculation
    wet_bulb = dry_bulb * math.atan(0.151977 * math.sqrt(relative_humidity + 8.313659)) + \
               math.atan(dry_bulb + relative_humidity) - math.atan(relative_humidity - 1.676331) + \
               0.00391838 * (relative_humidity)**(3/2) * math.atan(0.023101 * relative_humidity) - 4.686035
    
    # Ensure wet bulb is less than or equal to dry bulb
    return min(wet_bulb, dry_bulb)

def simulate_zone_temperatures(zones, outdoor_temp, hour, solar_ghi):
    """Simulate zone temperatures based on conditions and previous control actions.
    This now uses each VAV's thermal model for consistency."""
    zone_temps = {}
    
    # Define occupancy pattern (8 AM to 6 PM)
    is_occupied = 8 <= hour <= 18
    current_minute = 0  # We're simulating in 1-hour increments
    
    for vav_name, vav in zones.items():
        # Set occupancy based on schedule
        if is_occupied:
            # Simulate 1 person per 150 sq ft during occupied hours
            occupancy = max(1, int(vav.zone_area / 150))
            vav.set_occupancy(occupancy)
        else:
            vav.set_occupancy(0)
        
        # Update VAV based on current conditions
        vav.update(vav.zone_temp, vav.supply_air_temp)
        
        # Calculate VAV effect based on mode
        vav_effect = 0
        if vav.mode == "cooling":
            vav_effect = vav.damper_position  # Positive for cooling
        elif vav.mode == "heating" and vav.has_reheat:
            vav_effect = -vav.reheat_valve_position  # Negative for heating
        
        # Calculate temperature change using VAV's thermal model
        temp_change = vav.calculate_thermal_behavior(
            minutes=60,  # 1-hour simulation step
            outdoor_temp=outdoor_temp,
            vav_cooling_effect=vav_effect,
            time_of_day=(hour, current_minute)
        )
        
        # Update zone temperature
        vav.zone_temp += temp_change
        
        # Only reset if temperature is truly unrealistic
        if vav.zone_temp < 20 or vav.zone_temp > 120:
            vav.zone_temp = vav.zone_temp_setpoint
            
        # Store the new temperature
        zone_temps[vav_name] = vav.zone_temp
    
    return zone_temps

def calculate_chw_load(ahu1, ahu3, ahu4):
    """Calculate chilled water cooling load from AHU operations."""
    # Simple model - convert AHU cooling energy to tons
    chw_load = 0
    
    for ahu in [ahu1, ahu3, ahu4]:
        # Calculate load based on airflow and temperature difference
        if ahu.cooling_valve_position > 0:
            # Each 12,000 BTU/hr is 1 ton of cooling
            chw_load += ahu.cooling_energy / 12000
    
    return chw_load

def calculate_dx_load(ahu2):
    """Calculate DX cooling load from AHU operation."""
    # Simple model - convert AHU cooling energy to tons
    if ahu2.cooling_valve_position > 0:
        # Each 12,000 BTU/hr is 1 ton of cooling
        return ahu2.cooling_energy / 12000
    return 0

def calculate_hw_load(north_vavs, south_vavs, east_vavs, west_vavs):
    """Calculate hot water load from VAV reheat operations."""
    # Sum up the reheat energy from all VAVs with reheat
    hw_load = 0
    
    for vav in north_vavs + south_vavs + east_vavs + west_vavs:
        if vav.has_reheat and vav.reheat_valve_position > 0:
            # Convert BTU/hr to MBH (thousand BTU/hr)
            hw_load += vav.heating_energy / 1000
    
    return hw_load

def plot_results(hours, outdoor_temps, zone_temps, chiller_loads, chiller_cops, 
                tower_approaches, boiler_loads, boiler_efficiencies, ahu_airflows,
                cooling_energy, heating_energy, fan_energy):
    """Create comprehensive plots of simulation results."""
    # Create figure
    fig = plt.figure(figsize=(18, 24))
    gs = GridSpec(5, 2, figure=fig)
    
    # 1. Temperatures Plot
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(hours, outdoor_temps, 'k-', label='Outdoor Temp')
    
    for zone_type, temps in zone_temps.items():
        ax1.plot(hours, temps, label=f'{zone_type.capitalize()} Zones')
    
    ax1.set_ylabel('Temperature (°F)')
    ax1.set_title('Zone and Outdoor Temperatures')
    ax1.set_xticks(range(0, 25, 3))
    ax1.set_xticklabels([f'{h}:00' for h in range(0, 25, 3)])
    ax1.legend()
    ax1.grid(True)
    
    # 2. Chiller Loads
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.plot(hours, chiller_loads['water_cooled'], 'b-', label='Water-Cooled')
    ax2.plot(hours, chiller_loads['air_cooled'], 'r-', label='Air-Cooled')
    
    ax2.set_ylabel('Load (tons)')
    ax2.set_title('Chiller Loads')
    ax2.set_xticks(range(0, 25, 3))
    ax2.set_xticklabels([f'{h}:00' for h in range(0, 25, 3)])
    ax2.legend()
    ax2.grid(True)
    
    # 3. Chiller COPs
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.plot(hours, chiller_cops['water_cooled'], 'b-', label='Water-Cooled')
    ax3.plot(hours, chiller_cops['air_cooled'], 'r-', label='Air-Cooled')
    
    ax3.set_ylabel('COP')
    ax3.set_title('Chiller Efficiency (COP)')
    ax3.set_xticks(range(0, 25, 3))
    ax3.set_xticklabels([f'{h}:00' for h in range(0, 25, 3)])
    ax3.legend()
    ax3.grid(True)
    
    # 4. Cooling Tower Approach
    ax4 = fig.add_subplot(gs[2, 0])
    if tower_approaches:  # Only plot if we have data
        ax4.plot(hours, tower_approaches, 'g-')
        
        # Add outdoor wet bulb reference
        wb_temps = [estimate_wet_bulb(db, 50) for db in outdoor_temps]
        ax4_twin = ax4.twinx()
        ax4_twin.plot(hours, wb_temps, 'k--', alpha=0.5, label='Wet Bulb Temp')
        ax4_twin.set_ylabel('Wet Bulb Temp (°F)')
        ax4_twin.legend(loc='upper right')
    
    ax4.set_ylabel('Approach (°F)')
    ax4.set_title('Cooling Tower Approach Temperature')
    ax4.set_xticks(range(0, 25, 3))
    ax4.set_xticklabels([f'{h}:00' for h in range(0, 25, 3)])
    ax4.grid(True)
    
    # 5. Boiler Loads
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.plot(hours, boiler_loads['gas'], 'orange', label='Gas Boiler')
    ax5.plot(hours, boiler_loads['electric'], 'purple', label='Electric Boiler')
    
    ax5.set_ylabel('Load (MBH)')
    ax5.set_title('Boiler Loads')
    ax5.set_xticks(range(0, 25, 3))
    ax5.set_xticklabels([f'{h}:00' for h in range(0, 25, 3)])
    ax5.legend()
    ax5.grid(True)
    
    # 6. Boiler Efficiencies
    ax6 = fig.add_subplot(gs[3, 0])
    valid_gas_eff = [e for e in boiler_efficiencies['gas'] if e > 0]
    valid_electric_eff = [e for e in boiler_efficiencies['electric'] if e > 0]
    valid_hours_gas = [h for h, e in zip(hours, boiler_efficiencies['gas']) if e > 0]
    valid_hours_electric = [h for h, e in zip(hours, boiler_efficiencies['electric']) if e > 0]
    
    if valid_gas_eff:
        ax6.plot(valid_hours_gas, [e * 100 for e in valid_gas_eff], 'orange', label='Gas Boiler')
    if valid_electric_eff:
        ax6.plot(valid_hours_electric, [e * 100 for e in valid_electric_eff], 'purple', label='Electric Boiler')
    
    ax6.set_ylabel('Efficiency (%)')
    ax6.set_title('Boiler Efficiencies')
    ax6.set_xticks(range(0, 25, 3))
    ax6.set_xticklabels([f'{h}:00' for h in range(0, 25, 3)])
    ax6.legend()
    ax6.grid(True)
    
    # 7. AHU Airflows
    ax7 = fig.add_subplot(gs[3, 1])
    for ahu_name, airflows in ahu_airflows.items():
        ax7.plot(hours, airflows, label=ahu_name)
    
    ax7.set_ylabel('Airflow (CFM)')
    ax7.set_title('AHU Airflows')
    ax7.set_xticks(range(0, 25, 3))
    ax7.set_xticklabels([f'{h}:00' for h in range(0, 25, 3)])
    ax7.legend()
    ax7.grid(True)
    
    # 8. Energy Usage
    ax8 = fig.add_subplot(gs[4, :])
    ax8.plot(hours, cooling_energy, 'b-', label='Cooling Energy')
    ax8.plot(hours, heating_energy, 'r-', label='Heating Energy (Electric)')
    ax8.plot(hours, fan_energy, 'g-', label='Fan Energy')
    
    # Plot stacked total
    total = [c + h + f for c, h, f in zip(cooling_energy, heating_energy, fan_energy)]
    ax8.plot(hours, total, 'k--', label='Total Energy')
    
    ax8.set_xlabel('Hour of Day')
    ax8.set_ylabel('Power (kW)')
    ax8.set_title('Energy Usage')
    ax8.set_xticks(range(0, 25, 3))
    ax8.set_xticklabels([f'{h}:00' for h in range(0, 25, 3)])
    ax8.legend()
    ax8.grid(True)
    
    plt.tight_layout()
    plt.savefig('complete_system_results.png')
    print("Simulation results saved to complete_system_results.png")

if __name__ == "__main__":
    main()