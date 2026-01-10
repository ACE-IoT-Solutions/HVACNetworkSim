#!/usr/bin/env python3
"""Complete Building Simulation Example.

This example demonstrates a full building HVAC simulation with:
- Multiple AHUs with VAV boxes
- Chiller plant with cooling tower
- Boiler for heating
- Coordinated control sequences

This example does NOT include BACnet networking - see example_bacnet_simulation.py
for BACnet integration.
"""

import time

from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.chiller import Chiller
from src.cooling_tower import CoolingTower
from src.boiler import Boiler


def create_vav_boxes(ahu_name: str, count: int, orientations: list[str]) -> list[VAVBox]:
    """Create VAV boxes for an AHU.

    Args:
        ahu_name: Name of the parent AHU
        count: Number of VAV boxes to create
        orientations: Window orientations to cycle through

    Returns:
        List of VAVBox instances
    """
    vavs = []
    for i in range(1, count + 1):
        orientation = orientations[(i - 1) % len(orientations)]
        vav = VAVBox(
            name=f"{ahu_name}-VAV-{i:02d}",
            min_airflow=100,
            max_airflow=800,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=60 if orientation != "interior" else 0,
            window_orientation=orientation if orientation != "interior" else "north",
            thermal_mass=2.0 if orientation != "interior" else 3.0,
        )
        vavs.append(vav)
    return vavs


def create_chiller_plant():
    """Create a chiller with cooling tower.

    Returns:
        Tuple of (chiller, cooling_tower)
    """
    cooling_tower = CoolingTower(
        name="CT-1",
        capacity=600,  # tons
        design_approach=7,
        design_range=10,
        design_wet_bulb=78,
        min_speed=20,
        tower_type="counterflow",
        fan_power=50,
        num_cells=2,
    )

    chiller = Chiller(
        name="CH-1",
        cooling_type="water_cooled",
        capacity=500,  # tons
        design_cop=5.0,
        design_entering_condenser_temp=85,
        design_leaving_chilled_water_temp=44,
        min_part_load_ratio=0.1,
        design_chilled_water_flow=1000,
        design_condenser_water_flow=1200,
    )
    chiller.connect_cooling_tower(cooling_tower)

    return chiller, cooling_tower


def create_boiler_plant():
    """Create a boiler for heating.

    Returns:
        Boiler instance
    """
    return Boiler(
        name="B-1",
        fuel_type="gas",
        capacity=1000,  # MBH
        design_efficiency=0.85,
        design_entering_water_temp=160,
        design_leaving_water_temp=180,
        min_part_load_ratio=0.2,
        design_hot_water_flow=100,
        condensing=True,
        turndown_ratio=5.0,
    )


def print_status(
    minute: int,
    outdoor_temp: float,
    ahus: list[AirHandlingUnit],
    chiller: Chiller,
    boiler: Boiler,
    zone_temps: dict[str, float],
):
    """Print current system status."""
    hour = minute // 60
    min_in_hour = minute % 60

    print(f"\n{'='*70}")
    print(f"Time: {hour:02d}:{min_in_hour:02d} | Outdoor: {outdoor_temp:.1f}°F")
    print(f"{'='*70}")

    # AHU status
    for ahu in ahus:
        vav_modes = {}
        for vav in ahu.vav_boxes:
            mode = vav.mode
            vav_modes[mode] = vav_modes.get(mode, 0) + 1

        mode_str = ", ".join(f"{k}:{v}" for k, v in vav_modes.items())
        print(
            f"{ahu.name}: SAT={ahu.current_supply_air_temp:.1f}°F, "
            f"Flow={ahu.current_total_airflow:.0f} CFM, "
            f"Zones: {mode_str}"
        )

    # Plant status
    if chiller.current_load > 0:
        print(
            f"{chiller.name}: Load={chiller.current_load:.0f} tons, "
            f"COP={chiller.current_cop:.2f}, "
            f"LCWT={chiller.leaving_chilled_water_temp:.1f}°F"
        )
    else:
        print(f"{chiller.name}: Off")

    if boiler.is_on:
        print(
            f"{boiler.name}: Load={boiler.current_load:.0f} MBH, "
            f"Eff={boiler.current_efficiency*100:.1f}%, "
            f"LWT={boiler.leaving_water_temp:.1f}°F"
        )
    else:
        print(f"{boiler.name}: Off")

    # Sample zone temperatures
    temps = list(zone_temps.values())
    print(f"Zone temps: min={min(temps):.1f}°F, max={max(temps):.1f}°F, avg={sum(temps)/len(temps):.1f}°F")


def main():
    """Run a complete building simulation."""
    print("=" * 70)
    print("Complete Building HVAC Simulation")
    print("=" * 70)

    # Create AHUs with VAV boxes
    # AHU-1: 10 VAVs serving east and west perimeter zones
    vavs_1 = create_vav_boxes("AHU-1", 10, ["east", "west"])
    ahu_1 = AirHandlingUnit(
        name="AHU-1",
        supply_air_temp_setpoint=55,
        min_supply_air_temp=52,
        max_supply_air_temp=65,
        max_supply_airflow=10000,
        vav_boxes=vavs_1,
        enable_supply_temp_reset=True,
        cooling_type="chilled_water",
    )

    # AHU-2: 8 VAVs serving north, south, and interior zones
    vavs_2 = create_vav_boxes("AHU-2", 8, ["north", "south", "interior"])
    ahu_2 = AirHandlingUnit(
        name="AHU-2",
        supply_air_temp_setpoint=55,
        min_supply_air_temp=52,
        max_supply_air_temp=65,
        max_supply_airflow=8000,
        vav_boxes=vavs_2,
        enable_supply_temp_reset=True,
        cooling_type="chilled_water",
    )

    ahus = [ahu_1, ahu_2]

    # Create plant equipment
    chiller, cooling_tower = create_chiller_plant()
    boiler = create_boiler_plant()

    # Initialize zone temperatures
    zone_temps = {}
    for ahu in ahus:
        for vav in ahu.vav_boxes:
            zone_temps[vav.name] = 72.0  # Start at setpoint

    print(f"\nBuilding Configuration:")
    print(f"  AHUs: {len(ahus)}")
    print(f"  Total VAV boxes: {sum(len(ahu.vav_boxes) for ahu in ahus)}")
    print(f"  Chiller capacity: {chiller.capacity} tons")
    print(f"  Boiler capacity: {boiler.capacity} MBH")
    print(f"\nStarting 8-hour simulation (6 AM to 2 PM)...")
    print("(Press Ctrl+C to stop)")

    try:
        # Simulate 8 hours with 5-minute time steps (96 steps)
        for step in range(96):
            minute = step * 5
            hour = 6 + (minute // 60)
            min_in_hour = minute % 60

            # Calculate outdoor temperature (varies throughout day)
            # Peak at 2 PM (hour 14), low at 6 AM
            outdoor_temp = 65 + 20 * ((hour - 6) / 8)  # 65°F to 85°F

            # Calculate wet bulb (simplified - typically 10-15°F below dry bulb)
            wet_bulb = outdoor_temp - 12

            # Update AHUs and VAV boxes
            total_cooling_load = 0
            total_heating_load = 0

            for ahu in ahus:
                # Get zone temps for this AHU's VAVs
                ahu_zone_temps = {
                    vav.name: zone_temps[vav.name] for vav in ahu.vav_boxes
                }
                ahu.update(ahu_zone_temps, outdoor_temp=outdoor_temp)

                # Calculate cooling/heating loads
                energy = ahu.calculate_energy_usage()
                total_cooling_load += energy.get("cooling", 0) / 12000  # BTU/hr to tons
                total_heating_load += energy.get("heating", 0) / 1000  # BTU/hr to MBH

                # Update zone temperatures based on thermal behavior
                for vav in ahu.vav_boxes:
                    temp_change = vav.calculate_thermal_behavior(
                        minutes=5,
                        outdoor_temp=outdoor_temp,
                        vav_cooling_effect=vav.damper_position,
                        time_of_day=(hour, min_in_hour),
                    )
                    zone_temps[vav.name] = vav.zone_temp + temp_change

            # Update chiller if cooling is needed
            if total_cooling_load > chiller.capacity * chiller.min_part_load_ratio:
                chiller.update_load(
                    load=min(total_cooling_load, chiller.capacity),
                    entering_chilled_water_temp=54,
                    chilled_water_flow=800,
                    ambient_wet_bulb=wet_bulb,
                )
            else:
                chiller.current_load = 0
                chiller.current_cop = 0

            # Update boiler if heating is needed
            if total_heating_load > boiler.capacity * boiler.min_part_load_ratio:
                boiler.update_load(
                    load=min(total_heating_load, boiler.capacity),
                    entering_water_temp=160,
                    hot_water_flow=80,
                    ambient_temp=outdoor_temp,
                    simulation_time_step=5.0,
                )
            else:
                boiler.update_load(
                    load=0,
                    entering_water_temp=180,
                    hot_water_flow=0,
                    ambient_temp=outdoor_temp,
                    simulation_time_step=5.0,
                )

            # Print status every 30 minutes
            if step % 6 == 0:
                print_status(minute, outdoor_temp, ahus, chiller, boiler, zone_temps)

            time.sleep(0.05)  # Small delay for readability

    except KeyboardInterrupt:
        print("\n\nSimulation stopped by user.")

    print("\n" + "=" * 70)
    print("Simulation Complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
