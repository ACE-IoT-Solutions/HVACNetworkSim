#!/usr/bin/env python3
"""
Flexible BACnet HVAC simulator entrypoint.

This module serves as the main entry point for the container, supporting:
- Simple VAV simulation mode (single device on BACnet/IP)
- Brick schema-based simulation mode (routed networks per AHU)
- Multi-building campus mode with BBMD peers
- Auto-detection of container IP for BACnet networking

Network Architecture (Brick Mode):
    Each AHU gets its own BACnet network with its terminal units.
    Central plant equipment (chillers, boilers) on a separate network.
    This mirrors real building BACnet topology.

Network Architecture (Multi-Building Mode):
    Building 1 (Networks 1000-1999)       Building 2 (Networks 2000-2999)
            [BBMD-1] <---- WAN ----> [BBMD-2]
               |                        |
            [Router]                 [Router]
               |                        |
          [VLANs]                   [VLANs]

Environment Variables:
    BACNET_ADDRESS: Full BACnet address with CIDR (e.g., "172.26.0.20/16")
    BACNET_IP: BACnet IP address (auto-detected if not set)
    BACNET_SUBNET: Subnet mask in CIDR notation (default: 16)
    BACNET_PORT: BACnet UDP port (default: 47808)
    SIMULATION_MODE: "simple" or "brick" (default: simple)
    BRICK_TTL_FILE: Path to Brick TTL file (required for brick mode)
    MULTI_BUILDING_MODE: Enable multi-building campus simulation with BBMD
    INJECT_ERRORS: Enable error injection mode
    DUPLICATE_DEVICE_IDS: Number of duplicate device IDs to inject
    DUPLICATE_NETWORK_NUMBERS: Number of duplicate network numbers to inject
    DUPLICATE_ROUTERS: Number of duplicate routers to inject
"""

import asyncio
import logging
import math
import os
import random
import sys
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
from src.bacnet.bbmd import BBMDConfig, BBMDManager  # noqa: E402
from src.bacnet.errors import BACnetErrorInjector, ErrorInjectionConfig  # noqa: E402


def get_bacnet_address() -> str:
    """Get the BACnet address from environment variables.

    Returns:
        BACnet address string in format "IP/CIDR" (e.g., "172.26.0.20/16")
    """
    # First check for full address
    if os.getenv("BACNET_ADDRESS"):
        return os.getenv("BACNET_ADDRESS")

    # Otherwise construct from IP and subnet
    ip = os.getenv("BACNET_IP", "0.0.0.0")
    subnet = os.getenv("BACNET_SUBNET", "16")
    return f"{ip}/{subnet}"


async def run_simple_simulation():
    """Run a simple VAV box simulation with BACnet integration."""
    bacnet_address = get_bacnet_address()
    logger.info(f"Starting simple VAV simulation with BACnet address: {bacnet_address}")

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
    device = vav.create_bacpypes3_device(ip_address=bacnet_address)

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


async def run_brick_simulation():
    """
    Run a Brick schema-based simulation with routed BACnet networks.

    This creates a realistic building network topology:
    - Each AHU has its own BACnet network with its VAVs
    - Central plant equipment on a separate network
    """
    ttl_file = os.getenv("BRICK_TTL_FILE")

    if not ttl_file:
        logger.error("BRICK_TTL_FILE environment variable not set")
        sys.exit(1)

    if not os.path.exists(ttl_file):
        logger.error(f"Brick TTL file not found: {ttl_file}")
        sys.exit(1)

    logger.info("Starting Brick-based simulation with routed networks")
    logger.info(f"  TTL file: {ttl_file}")

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
    network_manager = create_building_networks_from_brick(building_structure)

    # Get BACnet address for the router
    bacnet_address = get_bacnet_address()
    bacnet_port = int(os.getenv("BACNET_PORT", "47808"))

    # Create the IP-to-VLAN router to bridge external traffic to internal VLANs
    logger.info("\nCreating IP-to-VLAN router...")
    router = network_manager.create_ip_to_vlan_router(
        ip_address=bacnet_address,
        bacnet_port=bacnet_port,
        device_id=999,
        device_name="HVAC-Building-Router",
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
            equipment=vav, network_info=network_info, device_name=f"VAV-{vav_name}"
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
            equipment=ahu, network_info=network_info, device_name=f"AHU-{ahu_name}"
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
                device_name=f"Chiller-{chiller_name}",
            )

    # Print network topology
    network_manager.print_network_topology()

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


async def run_multi_building_simulation():
    """
    Run a multi-building campus simulation with BBMD peers.

    This creates a realistic campus network topology:
    - Each building has its own BBMD
    - Buildings are connected via BBMD peer relationships
    - Each building has building-indexed network numbers
    - Optional error injection for training/testing
    """
    ttl_file = os.getenv("BRICK_TTL_FILE")

    if not ttl_file:
        logger.error("BRICK_TTL_FILE environment variable not set")
        sys.exit(1)

    if not os.path.exists(ttl_file):
        logger.error(f"Brick TTL file not found: {ttl_file}")
        sys.exit(1)

    logger.info("Starting Multi-Building Campus Simulation with BBMD")
    logger.info(f"  TTL file: {ttl_file}")

    # Check for rdflib
    try:
        import rdflib  # noqa: F401

        del rdflib
    except ImportError:
        logger.error("rdflib is required for multi-building simulation")
        sys.exit(1)

    # Import the BrickParser
    from src.brick.parser import BrickParser

    # Parse the Brick schema for multiple buildings
    logger.info(f"Parsing Brick schema: {ttl_file}")
    parser = BrickParser(ttl_file)
    campus = parser.extract_all_buildings()

    logger.info(f"Found campus: {campus.name}")
    logger.info(f"  Buildings: {len(campus.buildings)}")

    if len(campus.buildings) < 1:
        logger.warning("No buildings found in TTL file, falling back to simple simulation")
        await run_simple_simulation()
        return

    # Get BACnet configuration
    bacnet_address = get_bacnet_address()
    bacnet_port = int(os.getenv("BACNET_PORT", "47808"))
    ip_base = bacnet_address.split("/")[0]
    subnet = bacnet_address.split("/")[1] if "/" in bacnet_address else "24"

    # Create network manager in multi-building mode
    network_manager = BACnetNetworkManager(multi_building_mode=True)

    # Parse error injection configuration
    inject_errors = os.getenv("INJECT_ERRORS", "").lower() == "true"
    error_config = None
    error_injector = None

    if inject_errors:
        dup_ids = int(os.getenv("DUPLICATE_DEVICE_IDS", "0"))
        dup_nets = int(os.getenv("DUPLICATE_NETWORK_NUMBERS", "0"))
        dup_routers = int(os.getenv("DUPLICATE_ROUTERS", "0"))

        if dup_ids > 0 or dup_nets > 0 or dup_routers > 0:
            error_config = ErrorInjectionConfig(
                duplicate_device_ids=[(1000 + i, 1) for i in range(dup_ids)],
                duplicate_network_numbers=[(1001 + i * 100, 1) for i in range(dup_nets)],
                duplicate_routers=[1001 + i * 100 for i in range(dup_routers)],
            )
            error_injector = BACnetErrorInjector(error_config)
            logger.info("Error injection enabled:")
            logger.info(f"  Duplicate device IDs: {dup_ids}")
            logger.info(f"  Duplicate network numbers: {dup_nets}")
            logger.info(f"  Duplicate routers: {dup_routers}")

    # Create BBMD manager
    bbmd_manager = BBMDManager()
    bbmd_configs: List[BBMDConfig] = []

    # Register buildings and create BBMD configs
    logger.info("\nConfiguring buildings:")
    for idx, (building_name, building) in enumerate(campus.buildings.items()):
        building_index = network_manager.register_building(building_name)
        logger.info(
            f"  {building_name}: Index {building_index}, Networks {building_index * 1000}-{(building_index + 1) * 1000 - 1}"
        )

        # Create BBMD config for this building
        # Each building gets a unique IP (simulated - in real deployment these would be different IPs)
        building_ip = f"{ip_base}"  # In simulation, all on same IP
        bbmd_config = BBMDConfig(
            ip_address=f"{building_ip}/{subnet}",
            port=bacnet_port,
            device_name=f"BBMD-{building_name}",
            building_name=building_name,
        )
        bbmd_configs.append(bbmd_config)

        # Create networks for this building's equipment
        if building.ahus:
            # Create central plant network for this building
            network_manager.create_central_plant_network(
                building_name=building_name,
                building_index=building_index,
            )

            # Create AHU networks
            for ahu_idx, ahu_name in enumerate(building.ahus.keys()):
                network_manager.create_ahu_network(
                    ahu_name=ahu_name,
                    ahu_index=ahu_idx,
                    building_name=building_name,
                    building_index=building_index,
                )

    # Create peered BBMDs
    logger.info("\nCreating BBMD peers:")
    bbmd_apps = bbmd_manager.create_peer_bbmds(bbmd_configs, auto_peer=True)
    for building_name, bbmd_app in bbmd_apps.items():
        logger.info(f"  {building_name}: BBMD created")

    # Create IP-to-VLAN router for external access
    logger.info("\nCreating IP-to-VLAN router for external access...")
    router = network_manager.create_ip_to_vlan_router(
        ip_address=bacnet_address,
        bacnet_port=bacnet_port,
        device_id=999,
        device_name="Campus-Router",
    )

    if router:
        logger.info(f"Router created, BACnet/IP accessible on {bacnet_address}:{bacnet_port}")

    # Storage for simulation objects
    all_vavs: Dict[str, VAVBox] = {}
    all_ahus: Dict[str, AirHandlingUnit] = {}
    ahu_vav_map: Dict[str, List[VAVBox]] = {}

    # Create equipment for each building
    logger.info("\nCreating equipment:")
    for building_name, building in campus.buildings.items():
        logger.info(f"\n  Building: {building_name}")
        building_index = network_manager.buildings.get(building_name, 1)

        # Create VAVs
        for vav_name, vav_data in building.vavs.items():
            # Find which AHU this VAV belongs to
            ahu_name = None
            for ahu_id, ahu_info in building.ahus.items():
                if "vavs" in ahu_info and vav_name in ahu_info.get("vavs", []):
                    ahu_name = ahu_id
                    break

            # Default to first AHU if not found
            if not ahu_name and building.ahus:
                ahu_name = list(building.ahus.keys())[0]

            if not ahu_name:
                logger.warning(f"    {vav_name}: No AHU assignment, skipping")
                continue

            network_info = network_manager.get_network_for_ahu(ahu_name)
            if not network_info:
                logger.warning(f"    {vav_name}: No network for AHU {ahu_name}, skipping")
                continue

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

            app = network_manager.add_device_to_network(
                equipment=vav, network_info=network_info, device_name=f"VAV-{vav_name}"
            )

            if app:
                all_vavs[vav_name] = vav
                if ahu_name not in ahu_vav_map:
                    ahu_vav_map[ahu_name] = []
                ahu_vav_map[ahu_name].append(vav)

        # Create AHUs
        for ahu_name, ahu_data in building.ahus.items():
            network_info = network_manager.get_network_for_ahu(ahu_name)
            if not network_info:
                continue

            vav_list = ahu_vav_map.get(ahu_name, [])
            total_airflow = sum(v.max_airflow for v in vav_list) if vav_list else 10000

            ahu = AirHandlingUnit(
                name=ahu_name,
                cooling_type="chilled_water",
                supply_air_temp_setpoint=55,
                min_supply_air_temp=52,
                max_supply_air_temp=65,
                max_supply_airflow=total_airflow * 1.2,
                vav_boxes=vav_list,
                enable_supply_temp_reset=True,
            )

            app = network_manager.add_device_to_network(
                equipment=ahu, network_info=network_info, device_name=f"AHU-{ahu_name}"
            )

            if app:
                all_ahus[ahu_name] = ahu
                logger.info(
                    f"    {ahu_name}: Created with {len(vav_list)} VAVs on network {network_info.network_number}"
                )

        # Create central plant equipment
        central_plant = network_manager.get_central_plant_network(building_index)
        if central_plant:
            # Chillers
            for chiller_name in building.chillers:
                name = chiller_name if isinstance(chiller_name, str) else f"Chiller-{building_name}"
                chiller = Chiller(
                    name=name,
                    cooling_type="water_cooled",
                    capacity=500,
                    design_cop=5.0,
                    design_entering_condenser_temp=85,
                    design_leaving_chilled_water_temp=44,
                    min_part_load_ratio=0.1,
                    design_chilled_water_flow=1000,
                    design_condenser_water_flow=1200,
                )
                network_manager.add_device_to_network(
                    equipment=chiller, network_info=central_plant, device_name=f"Chiller-{name}"
                )
                logger.info(f"    {name}: Chiller on network {central_plant.network_number}")

            # Boilers
            for boiler_name in building.boilers:
                name = boiler_name if isinstance(boiler_name, str) else f"Boiler-{building_name}"
                boiler = Boiler(
                    name=name,
                    fuel_type="gas",
                    capacity=1000,
                    design_efficiency=0.85,
                    design_entering_water_temp=160,
                    design_leaving_water_temp=180,
                    min_part_load_ratio=0.2,
                    design_hot_water_flow=100,
                    condensing=True,
                    turndown_ratio=5.0,
                )
                network_manager.add_device_to_network(
                    equipment=boiler, network_info=central_plant, device_name=f"Boiler-{name}"
                )
                logger.info(f"    {name}: Boiler on network {central_plant.network_number}")

    # Inject errors if configured
    if error_injector:
        logger.info("\nInjecting errors:")
        injected = error_injector.apply_errors_to_network(network_manager)
        logger.info(f"  Injected {len(injected)} error devices")

    # Print network topology
    network_manager.print_network_topology()

    # Summary
    summary = network_manager.get_network_summary()
    logger.info(
        f"\nSimulation ready with {len(campus.buildings)} buildings, "
        f"{summary['total_networks']} networks, and {summary['total_devices']} devices"
    )

    # 24-hour simulation loop (same as brick mode)
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

            update_tasks = []
            for vav_name, vav in all_vavs.items():
                vav.set_occupancy(occupancy_count)
                vav.update(vav.zone_temp, supply_air_temp)

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

            for ahu_name, ahu in all_ahus.items():
                zone_temps = {}
                for vav in ahu_vav_map.get(ahu_name, []):
                    zone_temps[vav.name] = vav.zone_temp
                ahu.update(zone_temps=zone_temps, outdoor_temp=outdoor_temp)
                update_tasks.append(ahu.update_bacnet_device())

            if update_tasks:
                await asyncio.gather(*update_tasks, return_exceptions=True)

            avg_zone_temp = (
                sum(v.zone_temp for v in all_vavs.values()) / len(all_vavs) if all_vavs else 72.0
            )
            cooling_count = sum(1 for v in all_vavs.values() if v.mode == "cooling")
            heating_count = sum(1 for v in all_vavs.values() if v.mode == "heating")

            logger.info(
                f"Time: {hour:02d}:00 | Outdoor: {outdoor_temp:.1f}°F | "
                f"Avg Zone: {avg_zone_temp:.1f}°F | "
                f"Cooling: {cooling_count} | Heating: {heating_count} | "
                f"Buildings: {len(campus.buildings)} | VAVs: {len(all_vavs)}"
            )

            current_hour += 1
            await asyncio.sleep(60)

    except asyncio.CancelledError:
        logger.info("Simulation cancelled")


async def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("HVAC Network BACnet Simulator")
    logger.info("=" * 60)

    # Log configuration
    bacnet_address = get_bacnet_address()
    simulation_mode = os.getenv("SIMULATION_MODE", "simple")
    multi_building_mode = os.getenv("MULTI_BUILDING_MODE", "").lower() == "true"
    inject_errors = os.getenv("INJECT_ERRORS", "").lower() == "true"

    logger.info("Configuration:")
    logger.info(f"  BACnet Address: {bacnet_address}")
    logger.info(f"  BACnet Port: {os.getenv('BACNET_PORT', '47808')}")
    logger.info(f"  Simulation Mode: {simulation_mode}")
    logger.info(f"  Multi-Building Mode: {multi_building_mode}")

    if simulation_mode == "brick" or multi_building_mode:
        logger.info(f"  Brick TTL File: {os.getenv('BRICK_TTL_FILE', 'not set')}")

    if inject_errors:
        logger.info("  Error Injection: enabled")
        logger.info(f"    Duplicate Device IDs: {os.getenv('DUPLICATE_DEVICE_IDS', '0')}")
        logger.info(f"    Duplicate Networks: {os.getenv('DUPLICATE_NETWORK_NUMBERS', '0')}")
        logger.info(f"    Duplicate Routers: {os.getenv('DUPLICATE_ROUTERS', '0')}")

    logger.info("=" * 60)

    try:
        if multi_building_mode:
            await run_multi_building_simulation()
        elif simulation_mode == "brick":
            await run_brick_simulation()
        else:
            await run_simple_simulation()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
