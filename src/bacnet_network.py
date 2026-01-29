#!/usr/bin/env python3
"""
BACnet Network Manager for realistic building network topology.

This module creates a routed BACnet network architecture that mirrors real buildings:
- Each AHU has its own network with its terminal units (VAVs)
- Central plant equipment (chillers, boilers, cooling towers) on a separate network
- A BACnet IP-to-VLAN router connects all networks for inter-network communication
- Multi-building support with building-indexed network numbering

Single Building Network Topology:
    [External BACnet/IP Network - Port 47808]
        |
    [BACnet Router (IP-to-VLAN Bridge)]
        |
        +-- [Central Plant Network - Net 1]
        |       +-- Chiller(s)
        |       +-- Boiler(s)
        |       +-- Cooling Tower(s)
        |
        +-- [AHU-1 Network - Net 100]
        |       +-- AHU-1
        |       +-- VAV-1-1, VAV-1-2, ...
        |
        +-- [AHU-N Network - Net N*100]
                +-- AHU-N
                +-- VAV-N-1, VAV-N-2, ...

Multi-Building Network Topology:
    Building 1: Networks 1000-1999
        - Central Plant: Net 1001
        - AHU-1: Net 1100
        - AHU-2: Net 1200
    Building 2: Networks 2000-2999
        - Central Plant: Net 2001
        - AHU-1: Net 2100
        - AHU-2: Net 2200
    Building N: Networks N*1000 to (N+1)*1000-1
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.brick.campus import CampusStructure

from src.bacnet.device import get_package_version, generate_firmware_revision

logger = logging.getLogger(__name__)

try:
    from bacpypes3.vlan import VirtualNetwork
    from bacpypes3.app import Application  # noqa: F401 - used for isinstance checks

    BACPYPES_AVAILABLE = True
except ImportError:
    BACPYPES_AVAILABLE = False
    VirtualNetwork = None
    Application = None  # noqa: F811


@dataclass
class NetworkInfo:
    """Information about a BACnet network."""

    network_number: int
    name: str
    network: Optional[Any] = None  # VirtualNetwork instance
    devices: List[Any] = field(default_factory=list)  # Application instances
    ahu_name: Optional[str] = None  # Associated AHU name (if AHU network)
    building_name: Optional[str] = None  # Associated building name (multi-building mode)
    building_index: int = 0  # Building index (0 for single-building mode)


class BACnetNetworkManager:
    """
    Manages a routed BACnet network topology for building simulation.

    Creates separate networks for:
    - Central plant equipment (network 1 for single-building, or 1001, 2001, etc.)
    - Each AHU and its terminal units (networks 100, 200, ... or 1100, 1200, 2100, etc.)

    Multi-building mode uses building-indexed network numbering:
    - Building 1: Networks 1000-1999
    - Building 2: Networks 2000-2999
    - Building N: Networks N*1000 to (N+1)*1000-1
    """

    BACNET_IP_NETWORK = 65534  # External BACnet/IP network number (high number to avoid conflicts)
    CENTRAL_PLANT_NETWORK = 1
    AHU_NETWORK_BASE = 100  # AHU networks start at 100, 200, 300, etc.

    # Multi-building network allocation constants
    BUILDING_NETWORK_RANGE = 1000  # Each building gets 1000 network numbers
    BUILDING_CENTRAL_PLANT_OFFSET = 1  # Central plant at N*1000 + 1
    BUILDING_AHU_BASE_OFFSET = 100  # AHUs start at N*1000 + 100

    def __init__(self, multi_building_mode: bool = False):
        """Initialize the network manager.

        Args:
            multi_building_mode: If True, use building-indexed network numbering
        """
        if not BACPYPES_AVAILABLE:
            raise ImportError("BACpypes3 is required for BACnet network management")

        self.networks: Dict[int, NetworkInfo] = {}
        self.all_devices: List[Any] = []
        self.router_app: Optional[Any] = None
        self._next_device_id = 1000
        self._next_mac_counter: Dict[int, int] = {}  # Per-network MAC counter
        self.multi_building_mode = multi_building_mode
        self.buildings: Dict[str, int] = {}  # Building name -> building index

    def _get_next_mac(self, network_number: int) -> str:
        """Get the next available MAC address for a network.

        MAC address 0x01 is reserved for the router on each network.
        Device MAC addresses start at 0x02.
        """
        if network_number not in self._next_mac_counter:
            self._next_mac_counter[network_number] = 2  # Start at 2, 1 is reserved for router

        mac_num = self._next_mac_counter[network_number]
        self._next_mac_counter[network_number] += 1

        # Format as hex with proper padding
        return f"0x{mac_num:04x}"

    def _get_next_device_id(self) -> int:
        """Get the next available device ID."""
        device_id = self._next_device_id
        self._next_device_id += 1
        return device_id

    def _get_building_network_base(self, building_index: int) -> int:
        """Get the base network number for a building.

        Args:
            building_index: 0-based building index

        Returns:
            Base network number for the building
        """
        if not self.multi_building_mode or building_index == 0:
            return 0  # Single-building mode uses original numbering
        return (building_index + 1) * self.BUILDING_NETWORK_RANGE

    def register_building(self, building_name: str) -> int:
        """Register a building and get its index.

        Args:
            building_name: Name of the building

        Returns:
            Building index (0-based)
        """
        if building_name not in self.buildings:
            self.buildings[building_name] = len(self.buildings)
        return self.buildings[building_name]

    def create_central_plant_network(
        self, building_index: int = 0, building_name: Optional[str] = None
    ) -> NetworkInfo:
        """
        Create the central plant network for chillers, boilers, etc.

        Args:
            building_index: Building index for multi-building mode (0 for single building)
            building_name: Optional building name for identification

        Returns:
            NetworkInfo for the central plant network
        """
        if self.multi_building_mode and building_index > 0:
            base = self._get_building_network_base(building_index)
            network_number = base + self.BUILDING_CENTRAL_PLANT_OFFSET
            network_name = f"central-plant-bldg{building_index + 1}"
        else:
            network_number = self.CENTRAL_PLANT_NETWORK
            network_name = "central-plant"

        print(f"Creating Central Plant network (Network {network_number})")

        vlan = VirtualNetwork(network_name)

        network_info = NetworkInfo(
            network_number=network_number,
            name=network_name,
            network=vlan,
            devices=[],
            building_name=building_name,
            building_index=building_index,
        )

        self.networks[network_number] = network_info
        return network_info

    def create_ahu_network(
        self,
        ahu_name: str,
        ahu_index: int,
        building_index: int = 0,
        building_name: Optional[str] = None,
    ) -> NetworkInfo:
        """
        Create a network for an AHU and its terminal units.

        Args:
            ahu_name: Name of the AHU (e.g., "AHU1")
            ahu_index: Index of the AHU (0-based), used for network numbering
            building_index: Building index for multi-building mode (0 for single building)
            building_name: Optional building name for identification

        Returns:
            NetworkInfo for the AHU network
        """
        if self.multi_building_mode and building_index > 0:
            base = self._get_building_network_base(building_index)
            network_number = base + self.BUILDING_AHU_BASE_OFFSET + (ahu_index * 100)
            network_name = f"ahu-{ahu_name.lower()}-bldg{building_index + 1}"
        else:
            network_number = self.AHU_NETWORK_BASE + (ahu_index * 100)
            network_name = f"ahu-{ahu_name.lower()}"

        print(f"Creating AHU network for {ahu_name} (Network {network_number})")

        vlan = VirtualNetwork(network_name)

        network_info = NetworkInfo(
            network_number=network_number,
            name=network_name,
            network=vlan,
            devices=[],
            ahu_name=ahu_name,
            building_name=building_name,
            building_index=building_index,
        )

        self.networks[network_number] = network_info
        return network_info

    def create_ip_to_vlan_router(
        self,
        ip_address: str,
        bacnet_port: int = 47808,
        device_id: int = 999,
        device_name: str = "BACnet-Router",
    ) -> Optional[Any]:
        """
        Create an IP-to-VLAN router that bridges external BACnet/IP traffic
        to the internal virtual networks.

        This router has:
        - One BACnet/IP network port bound to a real IP address (for external access)
        - One virtual network port for each internal VLAN

        Args:
            ip_address: IP address with CIDR notation (e.g., "10.88.0.32/16")
            bacnet_port: UDP port for BACnet/IP (default: 47808)
            device_id: BACnet device ID for the router
            device_name: Name for the router device

        Returns:
            The router Application, or None if failed
        """
        if not self.networks:
            logger.warning("No networks created yet, cannot create router")
            return None

        # Parse IP address
        ip_parts = ip_address.split("/")
        ip_addr = ip_parts[0]
        subnet_bits = int(ip_parts[1]) if len(ip_parts) > 1 else 16

        # Convert subnet bits to mask
        subnet_mask = ".".join(
            str((0xFFFFFFFF << (32 - subnet_bits) >> (24 - 8 * i)) & 0xFF) for i in range(4)
        )

        logger.info(f"Creating IP-to-VLAN router: {device_name}")
        logger.info(f"  IP Address: {ip_addr}")
        logger.info(f"  Subnet Mask: {subnet_mask}")
        logger.info(f"  BACnet Port: {bacnet_port}")
        logger.info(f"  Connected VLANs: {len(self.networks)}")

        # Build the router configuration
        router_config = [
            # Device object
            {
                "apdu-segment-timeout": 1000,
                "apdu-timeout": 3000,
                "application-software-version": get_package_version(),
                "database-revision": 1,
                "firmware-revision": generate_firmware_revision(device_name),
                "max-apdu-length-accepted": 1024,
                "model-name": "ACE-RTR-9000",
                "number-of-apdu-retries": 3,
                "object-identifier": f"device,{device_id}",
                "object-name": device_name,
                "object-type": "device",
                "protocol-revision": 22,
                "protocol-version": 1,
                "segmentation-supported": "segmented-both",
                "system-status": "operational",
                "vendor-identifier": 999,
                "vendor-name": "ACEHVACNetwork",
                "description": "IP-to-VLAN Router for HVAC Simulation",
            },
            # BACnet/IP network port (external access)
            {
                "bacnet-ip-mode": "normal",
                "bacnet-ip-udp-port": bacnet_port,
                "changes-pending": False,
                "ip-address": ip_addr,
                "ip-subnet-mask": subnet_mask,
                "link-speed": 0.0,
                "mac-address": f"{ip_addr}:{bacnet_port}",
                "network-number": self.BACNET_IP_NETWORK,  # External BACnet/IP network
                "network-number-quality": "configured",
                "network-type": "ipv4",
                "object-identifier": "network-port,1",
                "object-name": "BACnet-IP-Port",
                "object-type": "network-port",
                "out-of-service": False,
                "protocol-level": "bacnet-application",
                "reliability": "no-fault-detected",
            },
        ]

        logger.info(f"    Port 1: BACnet/IP (Network {self.BACNET_IP_NETWORK})")

        # Add a virtual network port for each internal network
        port_id = 2
        for network_number, network_info in sorted(self.networks.items()):
            router_config.append(
                {
                    "changes-pending": False,
                    "mac-address": "0x01",  # Router is always MAC 0x01 on each VLAN
                    "network-interface-name": network_info.name,
                    "network-number": network_number,
                    "network-number-quality": "configured",
                    "network-type": "virtual",
                    "object-identifier": f"network-port,{port_id}",
                    "object-name": f"VLAN-{network_info.name}",
                    "object-type": "network-port",
                    "out-of-service": False,
                    "protocol-level": "bacnet-application",
                    "reliability": "no-fault-detected",
                }
            )
            logger.info(f"    Port {port_id}: {network_info.name} (Network {network_number})")
            port_id += 1

        try:
            # Create the router application
            router_app = Application.from_json(router_config)
            router_app.name = device_name
            self.router_app = router_app

            logger.info(f"Router created with {port_id - 1} network ports")
            return router_app

        except Exception as e:
            logger.exception(f"Error creating router: {e}")
            return None

    def add_device_to_network(
        self,
        equipment,
        network_info: NetworkInfo,
        device_id: Optional[int] = None,
        device_name: Optional[str] = None,
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

        print(
            f"  Adding {device_name} (ID: {device_id}, MAC: {mac_address}) to {network_info.name}"
        )

        # Create the BACnet device using the equipment's method
        app = equipment.create_bacpypes3_device(
            device_id=device_id,
            device_name=device_name,
            network_interface_name=network_info.name,
            mac_address=mac_address,
        )

        if app:
            network_info.devices.append(app)
            self.all_devices.append(app)

            # Store network info on the app for reference
            app.network_number = network_info.network_number
            app.network_name = network_info.name

        return app

    def get_network_for_ahu(
        self, ahu_name: str, building_name: Optional[str] = None
    ) -> Optional[NetworkInfo]:
        """Get the network associated with an AHU.

        Args:
            ahu_name: Name of the AHU
            building_name: Optional building name to filter by

        Returns:
            NetworkInfo for the AHU network, or None if not found
        """
        for network_info in self.networks.values():
            if network_info.ahu_name == ahu_name:
                if building_name is None or network_info.building_name == building_name:
                    return network_info
        return None

    def get_central_plant_network(self, building_index: int = 0) -> Optional[NetworkInfo]:
        """Get the central plant network.

        Args:
            building_index: Building index for multi-building mode

        Returns:
            NetworkInfo for the central plant network, or None if not found
        """
        if self.multi_building_mode and building_index > 0:
            base = self._get_building_network_base(building_index)
            network_number = base + self.BUILDING_CENTRAL_PLANT_OFFSET
            return self.networks.get(network_number)
        return self.networks.get(self.CENTRAL_PLANT_NETWORK)

    def get_networks_for_building(self, building_name: str) -> List[NetworkInfo]:
        """Get all networks associated with a building.

        Args:
            building_name: Name of the building

        Returns:
            List of NetworkInfo objects for the building
        """
        return [
            net_info
            for net_info in self.networks.values()
            if net_info.building_name == building_name
        ]

    def get_building_index(self, building_name: str) -> Optional[int]:
        """Get the index for a building.

        Args:
            building_name: Name of the building

        Returns:
            Building index, or None if not registered
        """
        return self.buildings.get(building_name)

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
                name = getattr(device, "name", str(device.device_object.objectIdentifier))
                dev_id = device.device_object.objectIdentifier[1]
                print(f"    +-- {name} (Device {dev_id})")

        # AHU networks
        for net_num in sorted(self.networks.keys()):
            if net_num == self.CENTRAL_PLANT_NETWORK:
                continue

            net = self.networks[net_num]
            print(f"\n[Network {net.network_number}] {net.name.upper()}")
            for device in net.devices:
                name = getattr(device, "name", str(device.device_object.objectIdentifier))
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
        summary: Dict[str, Any] = {
            "total_networks": len(self.networks),
            "total_devices": len(self.all_devices),
            "multi_building_mode": self.multi_building_mode,
            "buildings": dict(self.buildings) if self.buildings else {},
            "networks": {
                net_num: {
                    "name": net_info.name,
                    "ahu": net_info.ahu_name,
                    "building": net_info.building_name,
                    "building_index": net_info.building_index,
                    "device_count": len(net_info.devices),
                }
                for net_num, net_info in self.networks.items()
            },
        }
        return summary


def create_building_networks_from_brick(
    building_structure: Dict[str, Any],
    network_manager: Optional[BACnetNetworkManager] = None,
    building_index: int = 0,
    building_name: Optional[str] = None,
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
        building_index: Building index for multi-building mode (0 for single building)
        building_name: Optional building name for identification

    Returns:
        BACnetNetworkManager with networks created
    """
    if network_manager is None:
        network_manager = BACnetNetworkManager()

    # Register the building if in multi-building mode
    if building_name and network_manager.multi_building_mode:
        network_manager.register_building(building_name)

    # Create central plant network if there are central plant devices
    has_central_plant = (
        building_structure.get("chillers")
        or building_structure.get("boilers")
        or building_structure.get("cooling_towers")
    )

    if has_central_plant:
        network_manager.create_central_plant_network(
            building_index=building_index, building_name=building_name
        )

    # Create a network for each AHU
    ahus = building_structure.get("ahus", {})
    for ahu_index, (ahu_name, ahu_data) in enumerate(ahus.items()):
        network_manager.create_ahu_network(
            ahu_name, ahu_index, building_index=building_index, building_name=building_name
        )

    return network_manager


def create_campus_networks(
    campus_structure: "CampusStructure",
) -> BACnetNetworkManager:
    """
    Create a complete BACnet network topology from a CampusStructure.

    This function creates networks for all buildings in the campus,
    using building-indexed network numbering for multi-building support.

    Args:
        campus_structure: CampusStructure containing multiple BuildingStructure objects

    Returns:
        BACnetNetworkManager with networks for all buildings
    """
    # Import here to avoid circular import

    # Determine if multi-building mode is needed
    is_multi_building = campus_structure.is_multi_building()

    network_manager = BACnetNetworkManager(multi_building_mode=is_multi_building)

    # Create networks for each building
    for building_index, (building_name, building) in enumerate(campus_structure.buildings.items()):
        # Register the building
        network_manager.register_building(building_name)

        # Convert BuildingStructure to dict format for compatibility
        building_dict = {
            "ahus": building.ahus,
            "vavs": building.vavs,
            "zones": building.zones,
            "chillers": building.chillers,
            "boilers": building.boilers,
            "cooling_towers": building.cooling_towers,
        }

        create_building_networks_from_brick(
            building_structure=building_dict,
            network_manager=network_manager,
            building_index=building_index,
            building_name=building_name,
        )

    return network_manager


def get_vav_network_assignment(
    vav_name: str,
    building_structure: Dict[str, Any],
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
