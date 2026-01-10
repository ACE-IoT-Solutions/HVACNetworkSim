#!/usr/bin/env python3
"""
BACnet Network Manager for realistic building network topology.

This module creates a routed BACnet network architecture that mirrors real buildings:
- Each AHU has its own network with its terminal units (VAVs)
- Central plant equipment (chillers, boilers, cooling towers) on a separate network
- A BACnet router connects all networks for inter-network communication

Network Topology:
    [Central Plant Network - Net 1]
        |
        +-- Chiller(s)
        +-- Boiler(s)
        +-- Cooling Tower(s)
        |
    [BACnet Router]
        |
        +-- [AHU-1 Network - Net 100]
        |       +-- AHU-1
        |       +-- VAV-1-1, VAV-1-2, ...
        |
        +-- [AHU-2 Network - Net 200]
        |       +-- AHU-2
        |       +-- VAV-2-1, VAV-2-2, ...
        |
        +-- [AHU-N Network - Net N*100]
                +-- AHU-N
                +-- VAV-N-1, VAV-N-2, ...
"""

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

try:
    from bacpypes3.vlan import VirtualNetwork
    from bacpypes3.app import Application
    BACPYPES_AVAILABLE = True
except ImportError:
    BACPYPES_AVAILABLE = False
    VirtualNetwork = None


@dataclass
class NetworkInfo:
    """Information about a BACnet network."""
    network_number: int
    name: str
    network: Optional[Any] = None  # VirtualNetwork instance
    devices: List[Any] = field(default_factory=list)  # Application instances
    ahu_name: Optional[str] = None  # Associated AHU name (if AHU network)


class BACnetNetworkManager:
    """
    Manages a routed BACnet network topology for building simulation.

    Creates separate networks for:
    - Central plant equipment (network 1)
    - Each AHU and its terminal units (networks 100, 200, 300, ...)
    """

    CENTRAL_PLANT_NETWORK = 1
    AHU_NETWORK_BASE = 100  # AHU networks start at 100, 200, 300, etc.

    def __init__(self):
        """Initialize the network manager."""
        if not BACPYPES_AVAILABLE:
            raise ImportError("BACpypes3 is required for BACnet network management")

        self.networks: Dict[int, NetworkInfo] = {}
        self.all_devices: List[Any] = []
        self.router_app: Optional[Any] = None
        self._next_device_id = 1000
        self._next_mac_counter: Dict[int, int] = {}  # Per-network MAC counter

    def _get_next_mac(self, network_number: int) -> str:
        """Get the next available MAC address for a network."""
        if network_number not in self._next_mac_counter:
            self._next_mac_counter[network_number] = 1

        mac_num = self._next_mac_counter[network_number]
        self._next_mac_counter[network_number] += 1

        # Format as hex with proper padding
        return f"0x{mac_num:04x}"

    def _get_next_device_id(self) -> int:
        """Get the next available device ID."""
        device_id = self._next_device_id
        self._next_device_id += 1
        return device_id

    def create_central_plant_network(self) -> NetworkInfo:
        """
        Create the central plant network for chillers, boilers, etc.

        Returns:
            NetworkInfo for the central plant network
        """
        network_number = self.CENTRAL_PLANT_NETWORK
        network_name = "central-plant"

        print(f"Creating Central Plant network (Network {network_number})")

        vlan = VirtualNetwork(network_name)

        network_info = NetworkInfo(
            network_number=network_number,
            name=network_name,
            network=vlan,
            devices=[]
        )

        self.networks[network_number] = network_info
        return network_info

    def create_ahu_network(self, ahu_name: str, ahu_index: int) -> NetworkInfo:
        """
        Create a network for an AHU and its terminal units.

        Args:
            ahu_name: Name of the AHU (e.g., "AHU1")
            ahu_index: Index of the AHU (0-based), used for network numbering

        Returns:
            NetworkInfo for the AHU network
        """
        network_number = self.AHU_NETWORK_BASE + (ahu_index * 100)
        network_name = f"ahu-{ahu_name.lower()}"

        print(f"Creating AHU network for {ahu_name} (Network {network_number})")

        vlan = VirtualNetwork(network_name)

        network_info = NetworkInfo(
            network_number=network_number,
            name=network_name,
            network=vlan,
            devices=[],
            ahu_name=ahu_name
        )

        self.networks[network_number] = network_info
        return network_info

    def add_device_to_network(
        self,
        equipment,
        network_info: NetworkInfo,
        device_id: Optional[int] = None,
        device_name: Optional[str] = None
    ) -> Optional[Any]:
        """
        Add a device to a specific network.

        Args:
            equipment: The equipment object (VAVBox, AHU, Chiller, etc.)
            network_info: The network to add the device to
            device_id: Optional specific device ID
            device_name: Optional specific device name

        Returns:
            The BACpypes3 Application for the device, or None if failed
        """
        if device_id is None:
            device_id = self._get_next_device_id()

        if device_name is None:
            device_name = f"{equipment.__class__.__name__}-{equipment.name}"

        mac_address = self._get_next_mac(network_info.network_number)

        print(f"  Adding {device_name} (ID: {device_id}, MAC: {mac_address}) to {network_info.name}")

        # Create the BACnet device using the equipment's method
        app = equipment.create_bacpypes3_device(
            device_id=device_id,
            device_name=device_name,
            network_interface_name=network_info.name,
            mac_address=mac_address
        )

        if app:
            network_info.devices.append(app)
            self.all_devices.append(app)

            # Store network info on the app for reference
            app.network_number = network_info.network_number
            app.network_name = network_info.name

        return app

    def get_network_for_ahu(self, ahu_name: str) -> Optional[NetworkInfo]:
        """Get the network associated with an AHU."""
        for network_info in self.networks.values():
            if network_info.ahu_name == ahu_name:
                return network_info
        return None

    def get_central_plant_network(self) -> Optional[NetworkInfo]:
        """Get the central plant network."""
        return self.networks.get(self.CENTRAL_PLANT_NETWORK)

    def print_network_topology(self):
        """Print a visual representation of the network topology."""
        print("\n" + "=" * 60)
        print("BACnet Network Topology")
        print("=" * 60)

        # Central plant network
        if self.CENTRAL_PLANT_NETWORK in self.networks:
            net = self.networks[self.CENTRAL_PLANT_NETWORK]
            print(f"\n[Network {net.network_number}] {net.name.upper()}")
            for device in net.devices:
                name = getattr(device, 'name', str(device.device_object.objectIdentifier))
                dev_id = device.device_object.objectIdentifier[1]
                print(f"    +-- {name} (Device {dev_id})")

        # AHU networks
        for net_num in sorted(self.networks.keys()):
            if net_num == self.CENTRAL_PLANT_NETWORK:
                continue

            net = self.networks[net_num]
            print(f"\n[Network {net.network_number}] {net.name.upper()}")
            for device in net.devices:
                name = getattr(device, 'name', str(device.device_object.objectIdentifier))
                dev_id = device.device_object.objectIdentifier[1]
                print(f"    +-- {name} (Device {dev_id})")

        print("\n" + "=" * 60)
        total_devices = sum(len(n.devices) for n in self.networks.values())
        print(f"Total: {len(self.networks)} networks, {total_devices} devices")
        print("=" * 60 + "\n")

    def get_all_devices(self) -> List[Any]:
        """Get all devices across all networks."""
        return self.all_devices

    def get_network_summary(self) -> Dict[str, Any]:
        """Get a summary of the network configuration."""
        return {
            "total_networks": len(self.networks),
            "total_devices": len(self.all_devices),
            "networks": {
                net_num: {
                    "name": net_info.name,
                    "ahu": net_info.ahu_name,
                    "device_count": len(net_info.devices)
                }
                for net_num, net_info in self.networks.items()
            }
        }


def create_building_networks_from_brick(
    building_structure: Dict[str, Any],
    network_manager: Optional[BACnetNetworkManager] = None
) -> BACnetNetworkManager:
    """
    Create a complete BACnet network topology from a parsed Brick schema.

    This function:
    1. Creates the central plant network for chillers/boilers
    2. Creates a network for each AHU
    3. Returns a network manager with the topology configured

    Note: This only creates the networks - devices must be added separately
    using the equipment creation functions.

    Args:
        building_structure: Parsed Brick schema structure with keys:
            - ahus: Dict of AHU info with 'feeds' list of VAV names
            - vavs: Dict of VAV info
            - chillers: List of chiller names
            - boilers: List of boiler names
        network_manager: Optional existing manager to add to

    Returns:
        BACnetNetworkManager with networks created
    """
    if network_manager is None:
        network_manager = BACnetNetworkManager()

    # Create central plant network if there are central plant devices
    has_central_plant = (
        building_structure.get("chillers") or
        building_structure.get("boilers") or
        building_structure.get("cooling_towers")
    )

    if has_central_plant:
        network_manager.create_central_plant_network()

    # Create a network for each AHU
    ahus = building_structure.get("ahus", {})
    for ahu_index, (ahu_name, ahu_data) in enumerate(ahus.items()):
        network_manager.create_ahu_network(ahu_name, ahu_index)

    return network_manager


def get_vav_network_assignment(
    vav_name: str,
    building_structure: Dict[str, Any]
) -> Optional[str]:
    """
    Determine which AHU network a VAV should be assigned to.

    Args:
        vav_name: Name of the VAV
        building_structure: Parsed Brick schema

    Returns:
        Name of the AHU that feeds this VAV, or None if not found
    """
    ahus = building_structure.get("ahus", {})

    for ahu_name, ahu_data in ahus.items():
        feeds = ahu_data.get("feeds", [])
        if vav_name in feeds:
            return ahu_name

    return None
