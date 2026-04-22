#!/usr/bin/env python3
"""
Flexible BACnet HVAC simulator entrypoint.

This module serves as the main entry point for the container, supporting:
- Simple VAV simulation mode (single device on BACnet/IP)
- Brick schema-based simulation mode (routed networks per AHU)
- Auto-detection of container IP for BACnet networking

Network Architecture (Brick Mode):
    Each AHU gets its own BACnet network with its terminal units.
    Central plant equipment (chillers, boilers) on a separate network.
    This mirrors real building BACnet topology.

Network Architecture (Campus Mode):
    Each building runs in its own container with a dedicated IP subnet.
    External ace-acl-bbmd containers handle cross-building BACnet routing.
    See `./hvac-sim --campus` for multi-container campus simulation.

Environment Variables:
    BACNET_ADDRESS: Full BACnet address with CIDR (e.g., "172.26.0.20/16")
    BACNET_DEVICE_ID: Optional BACnet device instance number for simple mode
    BACNET_IP: BACnet IP address (auto-detected if not set)
    BACNET_NETWORK_NUMBER: Optional BACnet network number for simple mode
        and the campus building router's BACnet/IP network port
    BACNET_SUBNET: Subnet mask in CIDR notation (default: 16)
    BACNET_PORT: BACnet UDP port (default: 47808)
    SIMULATION_MODE: "simple" or "brick" (default: simple)
    BRICK_TTL_FILE: Path to Brick TTL file (required for brick mode)
    BUILDING_NAME: Building to simulate from a multi-building TTL (campus mode)
"""

import asyncio
import logging
import math
import os
import random
import sys
from pathlib import Path
from typing import Dict, List

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import simulation components (must be after logging config)
from src.vav_box import VAVBox  # noqa: E402
from src.ahu import AirHandlingUnit  # noqa: E402
from src.boiler import Boiler  # noqa: E402
from src.chiller import Chiller  # noqa: E402
from src.bacnet_network import (  # noqa: E402
    BACnetNetworkManager,
    create_building_networks_from_brick,
    get_vav_network_assignment,
)
from src.core.env_validation import (  # noqa: E402
    EnvironmentValidationError,
    normalize_bacnet_address,
    parse_boolean_value,
    parse_integer_value,
    validate_bacnet_device_id,
    validate_bacnet_network_number,
    validate_bacnet_port,
)


def get_bacnet_address() -> str:
    """Get the BACnet address from environment variables.

    Returns:
        BACnet address string in format "IP/CIDR" (e.g., "172.26.0.20/16")
    """
    return normalize_bacnet_address(
        address=os.getenv("BACNET_ADDRESS"),
        ip=os.getenv("BACNET_IP", "0.0.0.0"),
        subnet=os.getenv("BACNET_SUBNET", "16"),
    )


def get_bacnet_port() -> int:
    """Get the BACnet UDP port from the environment."""

    return validate_bacnet_port(os.getenv("BACNET_PORT", "47808"))


def get_bacnet_device_id() -> int | None:
    """Get an optional BACnet device instance number from the environment."""

    raw_value = os.getenv("BACNET_DEVICE_ID")
    if raw_value is None:
        return None
    return validate_bacnet_device_id(raw_value)


def get_bacnet_network_number() -> int | None:
    """Get an optional BACnet network number from the environment."""

    raw_value = os.getenv("BACNET_NETWORK_NUMBER")
    if raw_value is None or raw_value.strip() == "":
        return None
    return validate_bacnet_network_number(raw_value)


def get_boolean_env(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable with strict validation."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return parse_boolean_value(raw_value, variable_name=name)


def get_non_negative_env_int(name: str, default: str = "0") -> int:
    """Parse a non-negative integer environment variable."""

    return parse_integer_value(
        os.getenv(name, default), variable_name=name, min_value=0, max_value=10_000
    )


def get_simulation_mode() -> str:
    """Get the validated simulation mode."""

    simulation_mode = os.getenv("SIMULATION_MODE", "simple").strip().lower()
    if simulation_mode not in {"simple", "brick"}:
        raise EnvironmentValidationError(
            "SIMULATION_MODE must be 'simple' or 'brick' when running src/main.py"
        )
    return simulation_mode


async def run_simple_simulation():
    """Run a simple VAV box simulation with BACnet integration."""
    bacnet_address = get_bacnet_address()
    bacnet_port = get_bacnet_port()
    device_id = get_bacnet_device_id()
    network_number = get_bacnet_network_number()
    logger.info(
        "Starting simple VAV simulation with BACnet address: %s (port %d)",
        bacnet_address,
        bacnet_port,
    )
    if network_number is not None:
        logger.info("Using configured BACnet network number: %d", network_number)

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
        window_orientation="east",
        thermal_mass=2.0,
    )

    # Create BACnet device using auto-detected/configured IP
    logger.info("Creating BACpypes3 device...")
    device = vav.create_bacpypes3_device(
        device_id=device_id,
        ip_address=bacnet_address,
        bacnet_port=bacnet_port,
        network_number=network_number,
    )

    if device is None:
        logger.error("Failed to create BACnet device")
        return

    logger.info(
        f"Created BACnet device: {device.device_object.objectName} "
        f"(Device ID: {device.device_object.objectIdentifier[1]})"
    )

    # Display BACnet points
    logger.info("BACnet Points:")
    essential_points = ["zone_temp", "damper_position", "reheat_valve_position", "mode"]
    for point_name in essential_points:
        for obj in device.objectIdentifier.values():
            if hasattr(obj, "objectName") and obj.objectName == point_name:
                logger.info(f"  - {point_name}: {obj.presentValue} ({obj.objectType})")
                break

    # 24-hour outdoor temperature pattern
    outdoor_temps = {hour: 65 + 15 * math.sin(math.pi * (hour - 5) / 12) for hour in range(24)}

    # Office hours
    occupied_hours = [(8, 18)]
    occupancy = 5

    current_hour = 6  # Start at 6 AM
    supply_air_temp = 55  # °F

    try:
        while True:
            hour = current_hour % 24
            outdoor_temp = outdoor_temps[hour] + random.uniform(-1, 1)

            is_occupied = any(start <= hour < end for start, end in occupied_hours)
            occupancy_count = occupancy if is_occupied else 0

            vav.set_occupancy(occupancy_count)
            vav.update(vav.zone_temp, supply_air_temp)

            # Calculate thermal behavior
            vav_effect = 0
            if vav.mode == "cooling":
                vav_effect = vav.current_airflow / vav.max_airflow
            elif vav.mode == "heating" and vav.has_reheat:
                vav_effect = -vav.reheat_valve_position

            temp_change = vav.calculate_thermal_behavior(
                minutes=60,
                outdoor_temp=outdoor_temp,
                vav_cooling_effect=vav_effect,
                time_of_day=(hour, 0),
            )

            vav.zone_temp += temp_change
            await vav.update_bacnet_device()

            logger.info(
                f"Time: {hour:02d}:00, Outdoor: {outdoor_temp:.1f}°F, "
                f"Zone: {vav.zone_temp:.1f}°F, Mode: {vav.mode}, "
                f"Airflow: {vav.current_airflow:.0f} CFM"
            )

            current_hour += 1
            await asyncio.sleep(60)

    except asyncio.CancelledError:
        logger.info("Simulation cancelled")
    except Exception as e:
        logger.exception(f"Error in simulation: {e}")


async def run_brick_simulation(
    building_structure: dict = None, device_id_start: int = 1000, network_number_base: int = 0
):
    """
    Run a Brick schema-based simulation with routed BACnet networks.

    This creates a realistic building network topology:
    - Each AHU has its own BACnet network with its VAVs
    - Central plant equipment on a separate network

    Args:
        building_structure: Optional pre-parsed building structure dict.
            If not provided, reads from BRICK_TTL_FILE env var.
        device_id_start: Starting device ID for this building's devices.
            Each building in a campus must use a unique range to ensure
            globally unique device IDs across the BACnet internetwork.
        network_number_base: Base offset for network numbers.
            Each building in a campus must use a unique base to ensure
            globally unique network numbers (e.g., building 1 = 1000, building 2 = 2000).
    """
    if building_structure is None:
        ttl_file = os.getenv("BRICK_TTL_FILE")

        if not ttl_file:
            logger.error("BRICK_TTL_FILE environment variable not set")
            sys.exit(1)

        if not os.path.exists(ttl_file):
            logger.error(f"Brick TTL file not found: {ttl_file}")
            sys.exit(1)

        logger.info("Starting Brick-based simulation with routed networks")
        logger.info(f"  TTL file: {Path(ttl_file).name}")

        try:
            import rdflib  # noqa: F401 - availability check

            del rdflib
        except ImportError:
            logger.error("rdflib is required for Brick-based simulation")
            logger.error("Install with: pip install rdflib")
            sys.exit(1)

        # Import the BrickParser
        try:
            from src.brick.parser import BrickParser
        except ImportError as e:
            logger.error(f"Failed to import BrickParser: {e}")
            sys.exit(1)

        # Parse the Brick schema
        logger.info(f"Parsing Brick schema: {ttl_file}")
        parser = BrickParser(ttl_file)
        building_structure = parser.extract_all_equipment()
    else:
        logger.info("Starting Brick-based simulation with provided building structure")

    building_name = building_structure.get("building", {}).get("name", "Unknown")
    ahus = building_structure.get("ahus", {})
    vavs = building_structure.get("vavs", {})

    logger.info(f"Found building: {building_name}")
    logger.info(f"  AHUs: {len(ahus)}")
    logger.info(f"  VAVs: {len(vavs)}")
    logger.info(f"  Zones: {len(building_structure.get('zones', {}))}")

    if not ahus:
        logger.warning("No AHUs found in TTL file, falling back to simple simulation")
        await run_simple_simulation()
        return

    # Create the routed network topology
    logger.info("\nCreating routed BACnet network topology...")
    network_manager = BACnetNetworkManager(
        device_id_start=device_id_start, network_number_base=network_number_base
    )
    create_building_networks_from_brick(building_structure, network_manager=network_manager)

    # Get BACnet address for the router
    bacnet_address = get_bacnet_address()
    bacnet_port = get_bacnet_port()
    bacnet_network_number = get_bacnet_network_number()

    # Create the IP-to-VLAN router to bridge external traffic to internal VLANs
    # Router device ID is one below the device_id_start for this building
    # (e.g., building 1 = 999, building 2 = 1999)
    router_device_id = device_id_start - 1 if device_id_start > 0 else 999
    logger.info("\nCreating IP-to-VLAN router...")
    router = network_manager.create_ip_to_vlan_router(
        ip_address=bacnet_address,
        bacnet_port=bacnet_port,
        device_id=router_device_id,
        device_name="HVAC-Building-Router",
        ip_network_number=bacnet_network_number,
    )

    if not router:
        logger.error("Failed to create router, BACnet/IP will not be accessible externally")
    else:
        logger.info(f"Router created, BACnet/IP accessible on {bacnet_address}:{bacnet_port}")

    # Storage for simulation objects
    all_vavs: Dict[str, VAVBox] = {}
    all_ahus: Dict[str, AirHandlingUnit] = {}
    ahu_vav_map: Dict[str, List[VAVBox]] = {}  # AHU name -> list of VAVs

    # Create VAV boxes and add to appropriate AHU networks
    logger.info("\nCreating VAV boxes on their respective AHU networks:")

    for vav_name, vav_data in vavs.items():
        # Determine which AHU this VAV belongs to
        ahu_name = get_vav_network_assignment(vav_name, building_structure)

        if not ahu_name:
            logger.warning(f"  {vav_name}: No AHU assignment found, skipping")
            continue

        # Get the network for this AHU
        network_info = network_manager.get_network_for_ahu(ahu_name)
        if not network_info:
            logger.warning(f"  {vav_name}: No network found for AHU {ahu_name}, skipping")
            continue

        # Create the VAV box
        vav = VAVBox(
            name=vav_name,
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

        # Add to the AHU's network
        app = network_manager.add_device_to_network(
            equipment=vav,
            network_info=network_info,
            device_id=vav_data.get("device_id") if isinstance(vav_data, dict) else None,
            device_name=f"VAV-{vav_name}",
        )

        if app:
            all_vavs[vav_name] = vav

            # Track VAVs by AHU
            if ahu_name not in ahu_vav_map:
                ahu_vav_map[ahu_name] = []
            ahu_vav_map[ahu_name].append(vav)

    # Create AHUs and add to their networks
    logger.info("\nCreating AHUs on their networks:")

    for ahu_name, ahu_data in ahus.items():
        network_info = network_manager.get_network_for_ahu(ahu_name)
        if not network_info:
            logger.warning(f"  {ahu_name}: No network found, skipping")
            continue

        # Get the VAV boxes for this AHU
        vav_list = ahu_vav_map.get(ahu_name, [])

        # Calculate total airflow from VAVs
        total_airflow = sum(v.max_airflow for v in vav_list) if vav_list else 10000

        # Create the AHU
        ahu = AirHandlingUnit(
            name=ahu_name,
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=total_airflow * 1.2,  # 20% safety factor
            vav_boxes=vav_list,
            enable_supply_temp_reset=True,
        )

        # Add to the network
        app = network_manager.add_device_to_network(
            equipment=ahu,
            network_info=network_info,
            device_id=ahu_data.get("device_id") if isinstance(ahu_data, dict) else None,
            device_name=f"AHU-{ahu_name}",
        )

        if app:
            all_ahus[ahu_name] = ahu

    # Create central plant equipment if present
    central_plant_network = network_manager.get_central_plant_network()

    if central_plant_network:
        # Add boilers
        boilers_data = building_structure.get("boilers", {})
        if boilers_data:
            logger.info("\nCreating central plant equipment:")
            for boiler_name in boilers_data:
                boiler = Boiler(
                    name=boiler_name if isinstance(boiler_name, str) else "Boiler-1",
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
                network_manager.add_device_to_network(
                    equipment=boiler,
                    network_info=central_plant_network,
                    device_id=(
                        boilers_data.get(boiler_name, {}).get("device_id")
                        if isinstance(boilers_data.get(boiler_name), dict)
                        else None
                    ),
                    device_name=f"Boiler-{boiler_name}",
                )

        # Add chillers
        chillers_data = building_structure.get("chillers", {})
        for chiller_name in chillers_data:
            chiller = Chiller(
                name=chiller_name if isinstance(chiller_name, str) else "Chiller-1",
                cooling_type="water_cooled",
                capacity=500,  # tons
                design_cop=5.0,
                design_entering_condenser_temp=85,
                design_leaving_chilled_water_temp=44,
                min_part_load_ratio=0.1,
                design_chilled_water_flow=1000,
                design_condenser_water_flow=1200,
            )
            network_manager.add_device_to_network(
                equipment=chiller,
                network_info=central_plant_network,
                device_id=(
                    chillers_data.get(chiller_name, {}).get("device_id")
                    if isinstance(chillers_data.get(chiller_name), dict)
                    else None
                ),
                device_name=f"Chiller-{chiller_name}",
            )

    # Print network topology and device table
    network_manager.print_network_topology()
    network_manager.print_device_table(bacnet_address=bacnet_address)

    # Summary
    summary = network_manager.get_network_summary()
    logger.info(
        f"Simulation ready with {summary['total_networks']} networks "
        f"and {summary['total_devices']} devices"
    )

    # 24-hour outdoor temperature pattern
    outdoor_temps = {hour: 65 + 15 * math.sin(math.pi * (hour - 5) / 12) for hour in range(24)}

    occupied_hours = [(8, 18)]
    occupancy = 5
    current_hour = 6
    supply_air_temp = 55

    logger.info("\nStarting simulation loop (1 hour per minute)...")
    logger.info("Press Ctrl+C to stop\n")

    try:
        while True:
            hour = current_hour % 24
            outdoor_temp = outdoor_temps[hour] + random.uniform(-1, 1)
            is_occupied = any(start <= hour < end for start, end in occupied_hours)
            occupancy_count = occupancy if is_occupied else 0

            # Update all VAVs
            update_tasks = []
            for vav_name, vav in all_vavs.items():
                vav.set_occupancy(occupancy_count)
                vav.update(vav.zone_temp, supply_air_temp)

                # Calculate thermal behavior
                vav_effect = 0
                if vav.mode == "cooling":
                    vav_effect = vav.current_airflow / vav.max_airflow
                elif vav.mode == "heating" and vav.has_reheat:
                    vav_effect = -vav.reheat_valve_position

                temp_change = vav.calculate_thermal_behavior(
                    minutes=60,
                    outdoor_temp=outdoor_temp,
                    vav_cooling_effect=vav_effect,
                    time_of_day=(hour, 0),
                )

                vav.zone_temp += temp_change
                update_tasks.append(vav.update_bacnet_device())

            # Update all AHUs
            for ahu_name, ahu in all_ahus.items():
                # Collect zone temps from this AHU's VAVs
                zone_temps = {}
                for vav in ahu_vav_map.get(ahu_name, []):
                    zone_temps[vav.name] = vav.zone_temp
                ahu.update(zone_temps=zone_temps, outdoor_temp=outdoor_temp)
                update_tasks.append(ahu.update_bacnet_device())

            # Run all updates concurrently
            if update_tasks:
                await asyncio.gather(*update_tasks, return_exceptions=True)

            # Update router metric points
            if hasattr(network_manager, "router_metrics"):
                network_manager.router_metrics.update_points()

            # Log summary every hour
            avg_zone_temp = (
                sum(v.zone_temp for v in all_vavs.values()) / len(all_vavs) if all_vavs else 72.0
            )
            cooling_count = sum(1 for v in all_vavs.values() if v.mode == "cooling")
            heating_count = sum(1 for v in all_vavs.values() if v.mode == "heating")

            logger.info(
                f"Time: {hour:02d}:00 | Outdoor: {outdoor_temp:.1f}°F | "
                f"Avg Zone: {avg_zone_temp:.1f}°F | "
                f"Cooling: {cooling_count} | Heating: {heating_count} | "
                f"VAVs: {len(all_vavs)}"
            )

            current_hour += 1
            await asyncio.sleep(60)

    except asyncio.CancelledError:
        logger.info("Simulation cancelled")


async def run_single_building_from_campus():
    """
    Run a single building extracted from a campus TTL file.

    Reads BUILDING_NAME and BRICK_TTL_FILE env vars, parses the campus TTL,
    extracts the matching BuildingStructure, converts it to the dict format
    expected by run_brick_simulation(), and delegates to it.

    This is used when each building runs in its own container as part of
    a multi-container campus simulation with real podman networks and BBMDs.
    """
    building_name = os.getenv("BUILDING_NAME")
    ttl_file = os.getenv("BRICK_TTL_FILE")

    if not building_name:
        logger.error("BUILDING_NAME environment variable not set")
        sys.exit(1)

    if not ttl_file:
        logger.error("BRICK_TTL_FILE environment variable not set")
        sys.exit(1)

    if not os.path.exists(ttl_file):
        logger.error(f"Brick TTL file not found: {ttl_file}")
        sys.exit(1)

    logger.info(f"Starting single-building simulation for: {building_name}")
    logger.info(f"  TTL file: {Path(ttl_file).name}")

    try:
        import rdflib  # noqa: F401

        del rdflib
    except ImportError:
        logger.error("rdflib is required for campus simulation")
        sys.exit(1)

    from src.brick.parser import BrickParser

    # Parse the campus TTL and extract all buildings
    parser = BrickParser(ttl_file)
    campus = parser.extract_all_buildings()

    # Find the matching building
    building = campus.get_building(building_name)
    if not building:
        available = list(campus.buildings.keys())
        logger.error(f"Building '{building_name}' not found in TTL file")
        logger.error(f"  Available buildings: {available}")
        sys.exit(1)

    logger.info(f"Found building: {building.name}")
    logger.info(f"  AHUs: {len(building.ahus)}")
    logger.info(f"  VAVs: {len(building.vavs)}")
    logger.info(f"  Zones: {len(building.zones)}")
    logger.info(f"  Chillers: {len(building.chillers)}")
    logger.info(f"  Boilers: {len(building.boilers)}")

    # Compute building index (1-based) for unique device ID and network number ranges.
    # BACnet requires globally unique device IDs AND network numbers across the internetwork.
    # Each building gets a range of 1000: building 1 = 1000-1999, building 2 = 2000-2999, etc.
    building_names = list(campus.buildings.keys())
    building_index = building_names.index(building_name) + 1  # 1-based
    device_id_start = building_index * BACnetNetworkManager.BUILDING_DEVICE_ID_RANGE
    network_number_base = building_index * BACnetNetworkManager.BUILDING_NETWORK_RANGE
    logger.info(f"  Building index: {building_index}")
    logger.info(f"  Device ID range: {device_id_start}-{device_id_start + 999}")
    logger.info(f"  Network number base: {network_number_base}")

    # Convert BuildingStructure to the dict format expected by run_brick_simulation()
    building_dict = {
        "building": {"name": building.name, "area": building.area},
        "ahus": building.ahus,
        "vavs": building.vavs,
        "zones": building.zones,
        "chillers": building.chillers,
        "boilers": building.boilers,
    }

    await run_brick_simulation(
        building_structure=building_dict,
        device_id_start=device_id_start,
        network_number_base=network_number_base,
    )


async def main():
    """Main entry point."""
    try:
        logger.info("=" * 60)
        logger.info("HVAC Network BACnet Simulator")
        logger.info("=" * 60)

        # Log configuration after validating env-driven settings.
        bacnet_address = get_bacnet_address()
        bacnet_port = get_bacnet_port()
        bacnet_device_id = get_bacnet_device_id()
        bacnet_network_number = get_bacnet_network_number()
        simulation_mode = get_simulation_mode()
        building_name = os.getenv("BUILDING_NAME", "").strip()
        ttl_file = os.getenv("BRICK_TTL_FILE", "")

        logger.info("Configuration:")
        logger.info(f"  BACnet Address: {bacnet_address}")
        logger.info(f"  BACnet Port: {bacnet_port}")
        if bacnet_device_id is not None:
            logger.info(f"  BACnet Device ID: {bacnet_device_id}")
        if bacnet_network_number is not None:
            logger.info(f"  BACnet Network Number: {bacnet_network_number}")
        logger.info(f"  Simulation Mode: {simulation_mode}")
        if building_name:
            logger.info(f"  Building Name: {building_name}")

        if simulation_mode == "brick" or building_name:
            logger.info(f"  Brick TTL File: {Path(ttl_file).name if ttl_file else 'not set'}")

        logger.info("=" * 60)

        if building_name and simulation_mode == "brick":
            await run_single_building_from_campus()
        elif simulation_mode == "brick":
            await run_brick_simulation()
        else:
            await run_simple_simulation()
    except EnvironmentValidationError as e:
        logger.error("Invalid environment configuration: %s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
