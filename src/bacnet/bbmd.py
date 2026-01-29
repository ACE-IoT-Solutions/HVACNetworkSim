"""BACnet Broadcast Management Device (BBMD) configuration and management.

This module provides configuration and management for BBMDs, which enable
BACnet/IP communication between buildings across WAN connections.

BBMD Network Architecture:
    Building 1                              Building 2
    [BBMD-1] <---- WAN (Internet) ----> [BBMD-2]
       |                                    |
    [Router-1]                           [Router-2]
       |                                    |
    [Internal VLANs]                    [Internal VLANs]

Each BBMD maintains a Broadcast Distribution Table (BDT) containing
the IP addresses of peer BBMDs. When a broadcast message is received,
the BBMD forwards it to all peers in the BDT.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.bacnet.device import (
    get_package_version,
    generate_firmware_revision,
)
from src.core.constants import (
    BACNET_DEFAULT_PORT,
    BACNET_VENDOR_ID,
    BACNET_VENDOR_NAME,
    BACNET_MAX_APDU_LENGTH,
    BACNET_PROTOCOL_VERSION,
    BACNET_PROTOCOL_REVISION,
)

logger = logging.getLogger(__name__)

try:
    from bacpypes3.app import Application

    BACPYPES_AVAILABLE = True
except ImportError:
    BACPYPES_AVAILABLE = False
    Application = None  # type: ignore


@dataclass
class BDTEntry:
    """Entry in the Broadcast Distribution Table.

    Attributes:
        ip_address: IP address of the peer BBMD
        port: UDP port (default 47808)
        mask: Broadcast distribution mask (default 255.255.255.255)
    """

    ip_address: str
    port: int = BACNET_DEFAULT_PORT
    mask: str = "255.255.255.255"


@dataclass
class BBMDConfig:
    """Configuration for a BACnet Broadcast Management Device.

    Attributes:
        ip_address: IP address of this BBMD with CIDR notation
        port: UDP port for BACnet/IP (default 47808)
        device_id: BACnet device ID
        device_name: Name for the BBMD device
        bdt_entries: List of peer BBMD entries in the BDT
        building_name: Associated building name
        foreign_device_ttl: Time-to-live for foreign device registrations (seconds)
    """

    ip_address: str
    port: int = BACNET_DEFAULT_PORT
    device_id: Optional[int] = None
    device_name: Optional[str] = None
    bdt_entries: List[BDTEntry] = field(default_factory=list)
    building_name: Optional[str] = None
    foreign_device_ttl: int = 300  # 5 minutes

    def add_peer(
        self, ip_address: str, port: int = BACNET_DEFAULT_PORT, mask: str = "255.255.255.255"
    ) -> None:
        """Add a peer BBMD to the BDT.

        Args:
            ip_address: IP address of the peer BBMD
            port: UDP port (default 47808)
            mask: Broadcast distribution mask
        """
        self.bdt_entries.append(BDTEntry(ip_address=ip_address, port=port, mask=mask))


class BBMDManager:
    """Manager for creating and configuring BBMDs.

    This class handles the creation of BBMD devices that enable
    inter-building BACnet communication.
    """

    # BBMD device IDs start at 900 (below router at 999)
    BBMD_BASE_DEVICE_ID = 900

    def __init__(self):
        """Initialize the BBMD manager."""
        if not BACPYPES_AVAILABLE:
            raise ImportError("BACpypes3 is required for BBMD management")

        self.bbmds: Dict[str, Any] = {}  # Building name -> BBMD Application
        self._next_bbmd_id = self.BBMD_BASE_DEVICE_ID

    def _get_next_bbmd_id(self) -> int:
        """Get the next available BBMD device ID."""
        device_id = self._next_bbmd_id
        self._next_bbmd_id += 1
        return device_id

    def create_bbmd(
        self,
        config: BBMDConfig,
        internal_networks: Optional[Dict[int, Any]] = None,
    ) -> Optional[Any]:
        """Create a BBMD device.

        The BBMD has:
        - One BACnet/IP network port configured as BBMD
        - Optional connections to internal virtual networks

        Args:
            config: BBMD configuration
            internal_networks: Optional dict of network_number -> NetworkInfo
                              for internal VLAN connections

        Returns:
            BACpypes3 Application for the BBMD, or None if failed
        """
        # Set defaults
        device_id = config.device_id or self._get_next_bbmd_id()
        device_name = config.device_name or f"BBMD-{config.building_name or device_id}"

        # Parse IP address
        ip_parts = config.ip_address.split("/")
        ip_addr = ip_parts[0]
        subnet_bits = int(ip_parts[1]) if len(ip_parts) > 1 else 24

        # Convert subnet bits to mask
        subnet_mask = ".".join(
            str((0xFFFFFFFF << (32 - subnet_bits) >> (24 - 8 * i)) & 0xFF) for i in range(4)
        )

        logger.info(f"Creating BBMD: {device_name}")
        logger.info(f"  IP Address: {ip_addr}")
        logger.info(f"  Port: {config.port}")
        logger.info(f"  BDT Entries: {len(config.bdt_entries)}")

        # Build the BBMD configuration
        bbmd_config = [
            # Device object
            {
                "apdu-segment-timeout": 1000,
                "apdu-timeout": 3000,
                "application-software-version": get_package_version(),
                "database-revision": 1,
                "firmware-revision": generate_firmware_revision(device_name),
                "max-apdu-length-accepted": BACNET_MAX_APDU_LENGTH,
                "model-name": "ACE-BBMD-8000",
                "number-of-apdu-retries": 3,
                "object-identifier": f"device,{device_id}",
                "object-name": device_name,
                "object-type": "device",
                "protocol-revision": BACNET_PROTOCOL_REVISION,
                "protocol-version": BACNET_PROTOCOL_VERSION,
                "segmentation-supported": "segmented-both",
                "system-status": "operational",
                "vendor-identifier": BACNET_VENDOR_ID,
                "vendor-name": BACNET_VENDOR_NAME,
                "description": f"BBMD for {config.building_name or 'building'}",
            },
            # BACnet/IP network port configured as BBMD
            {
                "bacnet-ip-mode": "bbmd",
                "bacnet-ip-udp-port": config.port,
                "changes-pending": False,
                "ip-address": ip_addr,
                "ip-subnet-mask": subnet_mask,
                "link-speed": 0.0,
                "mac-address": f"{ip_addr}:{config.port}",
                "network-number": 65534,  # Standard BACnet/IP network
                "network-number-quality": "configured",
                "network-type": "ipv4",
                "object-identifier": "network-port,1",
                "object-name": "BBMD-Port",
                "object-type": "network-port",
                "out-of-service": False,
                "protocol-level": "bacnet-application",
                "reliability": "no-fault-detected",
            },
        ]

        # Add BDT entries to the network port configuration
        if config.bdt_entries:
            bdt_list = []
            for entry in config.bdt_entries:
                bdt_list.append(
                    {
                        "bbmd-address": f"{entry.ip_address}:{entry.port}",
                        "broadcast-mask": entry.mask,
                    }
                )
            bbmd_config[1]["bbmd-broadcast-distribution-table"] = bdt_list

        # Add internal network ports if provided
        if internal_networks:
            port_id = 2
            for network_number, network_info in sorted(internal_networks.items()):
                bbmd_config.append(
                    {
                        "changes-pending": False,
                        "mac-address": "0x01",  # BBMD/Router is MAC 0x01
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
            # Create the BBMD application
            bbmd_app = Application.from_json(bbmd_config)
            bbmd_app.name = device_name

            # Store reference
            if config.building_name:
                self.bbmds[config.building_name] = bbmd_app

            logger.info(f"BBMD created successfully: {device_name}")
            return bbmd_app

        except Exception as e:
            logger.exception(f"Error creating BBMD: {e}")
            return None

    def get_bbmd(self, building_name: str) -> Optional[Any]:
        """Get the BBMD for a building.

        Args:
            building_name: Name of the building

        Returns:
            BBMD Application, or None if not found
        """
        return self.bbmds.get(building_name)

    def create_peer_bbmds(
        self,
        configs: List[BBMDConfig],
        auto_peer: bool = True,
    ) -> Dict[str, Any]:
        """Create multiple BBMDs configured as peers.

        This is a convenience method that creates BBMDs for multiple
        buildings and automatically configures them as peers.

        Args:
            configs: List of BBMD configurations
            auto_peer: If True, automatically add all other BBMDs as peers

        Returns:
            Dict mapping building names to BBMD Applications
        """
        # If auto_peer, add all other BBMDs as peers to each config
        if auto_peer:
            for i, config in enumerate(configs):
                for j, other_config in enumerate(configs):
                    if i != j:
                        # Extract just the IP from the CIDR notation
                        other_ip = other_config.ip_address.split("/")[0]
                        config.add_peer(other_ip, other_config.port)

        # Create all BBMDs
        results = {}
        for config in configs:
            bbmd = self.create_bbmd(config)
            if bbmd and config.building_name:
                results[config.building_name] = bbmd

        return results


def create_campus_bbmds(
    building_ips: Dict[str, str],
    base_port: int = BACNET_DEFAULT_PORT,
) -> BBMDManager:
    """Create BBMDs for a campus with multiple buildings.

    This is a convenience function that creates peered BBMDs
    for all buildings in a campus.

    Args:
        building_ips: Dict mapping building names to IP addresses (with CIDR)
        base_port: Base UDP port (default 47808)

    Returns:
        BBMDManager with all BBMDs created
    """
    manager = BBMDManager()

    configs = []
    for building_name, ip_address in building_ips.items():
        config = BBMDConfig(
            ip_address=ip_address,
            port=base_port,
            device_name=f"BBMD-{building_name}",
            building_name=building_name,
        )
        configs.append(config)

    manager.create_peer_bbmds(configs, auto_peer=True)
    return manager
