#!/usr/bin/env python3
"""Simple VAV Box Example.

This example demonstrates basic VAV box operation without BACnet networking.
It shows how to create a VAV box, update its state, and observe its behavior.
"""

import time

from src.vav_box import VAVBox


def main():
    """Run a simple VAV box simulation."""
    # Create a VAV box with thermal zone properties
    vav = VAVBox(
        name="VAV-101",
        min_airflow=100,  # CFM
        max_airflow=800,  # CFM
        zone_temp_setpoint=72,  # °F
        deadband=2,  # °F
        discharge_air_temp_setpoint=55,  # °F
        has_reheat=True,
        zone_area=400,  # ft²
        zone_volume=3200,  # ft³
        window_area=60,  # ft²
        window_orientation="east",
        thermal_mass=2.0,
    )

    print("=" * 60)
    print("Simple VAV Box Simulation")
    print("=" * 60)
    print(f"VAV: {vav.name}")
    print(f"Zone setpoint: {vav.zone_temp_setpoint}°F")
    print(f"Deadband: {vav.deadband}°F")
    print(f"Airflow range: {vav.min_airflow}-{vav.max_airflow} CFM")
    print("=" * 60)

    # Initialize zone temperature
    zone_temp = 76.0  # Start warm (need cooling)
    supply_air_temp = 55.0  # Supply air from AHU
    outdoor_temp = 85.0

    print("\nStarting simulation (Ctrl+C to stop)...")
    print("-" * 60)

    try:
        for minute in range(60):  # Simulate 1 hour
            # Update the VAV box
            vav.update(zone_temp=zone_temp, supply_air_temp=supply_air_temp)

            # Calculate thermal behavior (zone temperature change)
            temp_change = vav.calculate_thermal_behavior(
                minutes=1,
                outdoor_temp=outdoor_temp,
                vav_cooling_effect=vav.damper_position,
                time_of_day=(12, minute),  # Noon
            )

            # Update zone temperature
            zone_temp += temp_change

            # Print status every 5 minutes
            if minute % 5 == 0:
                print(
                    f"Minute {minute:02d}: "
                    f"Zone={zone_temp:.1f}°F, "
                    f"Mode={vav.mode}, "
                    f"Damper={vav.damper_position*100:.0f}%, "
                    f"Airflow={vav.current_airflow:.0f} CFM"
                )

            time.sleep(0.1)  # Small delay for readability

    except KeyboardInterrupt:
        print("\nSimulation stopped.")

    print("-" * 60)
    print("Final State:")
    print(f"  Zone Temperature: {zone_temp:.1f}°F")
    print(f"  Mode: {vav.mode}")
    print(f"  Damper Position: {vav.damper_position*100:.0f}%")
    print(f"  Current Airflow: {vav.current_airflow:.0f} CFM")
    if vav.has_reheat:
        print(f"  Reheat Valve: {vav.reheat_valve_position*100:.0f}%")


if __name__ == "__main__":
    main()
