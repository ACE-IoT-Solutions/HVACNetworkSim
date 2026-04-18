"""BACnet Broadcast Management Device (BBMD) configuration dataclasses.

These dataclasses describe BBMD configuration for campus simulations.
Actual BBMD instances are run as external ace-acl-bbmd containers
(see `./hvac-sim --campus` and `campus/generate_campus.py`).
"""

from dataclasses import dataclass, field
from typing import List, Optional

from src.core.constants import BACNET_DEFAULT_PORT


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
