"""
BACnet device configuration and creation.

This module provides configuration dataclasses and functions for creating
BACnet devices from equipment. It separates the BACnet device creation
logic from the equipment classes themselves.

Usage:
    from src.bacnet.device import BACnetDeviceConfig, create_bacnet_device

    config = BACnetDeviceConfig(
        device_id=1001,
        device_name="VAV-101",
        ip_address="172.26.0.20/16"
    )
    app = create_bacnet_device(equipment, config)
"""

import hashlib
import logging
from dataclasses import dataclass
from importlib.metadata import version, PackageNotFoundError
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.core.constants import (
    BACNET_DEFAULT_PORT,
    BACNET_VENDOR_ID,
    BACNET_VENDOR_NAME,
    BACNET_MAX_APDU_LENGTH,
    BACNET_PROTOCOL_VERSION,
    BACNET_PROTOCOL_REVISION,
)

if TYPE_CHECKING:
    from bacpypes3.app import Application

logger = logging.getLogger(__name__)


def hex_to_padded_octets(hex_string: str) -> str:
    """
    Convert a hex string to properly formatted BACnet MAC address.

    Args:
        hex_string: Hex string like "0x1" or "1"

    Returns:
        Formatted hex string like "0x01"
    """
    hex_string = hex_string.replace("0x", "")
    if len(hex_string) % 2 != 0:
        hex_string = "0" + hex_string
    return "0x" + "".join([hex_string[i : i + 2] for i in range(0, len(hex_string), 2)])


# Equipment class name to model name mapping
EQUIPMENT_MODEL_NAMES: Dict[str, str] = {
    "VAVBox": "ACE-VAV-1000",
    "AirHandlingUnit": "ACE-AHU-2000",
    "Chiller": "ACE-CH-3000",
    "Boiler": "ACE-BLR-4000",
    "CoolingTower": "ACE-CT-5000",
    "Building": "ACE-BMS-6000",
}

DEFAULT_MODEL_NAME = "ACE-SIM-1000"


def get_package_version() -> str:
    """
    Get the version of the hvacnetwork package.

    Returns:
        Version string, or "0.0.0-dev" if not installed as a package.
    """
    try:
        return version("hvacnetwork")
    except PackageNotFoundError:
        return "0.0.0-dev"


def generate_firmware_revision(device_name: str) -> str:
    """
    Generate a firmware revision string from package version and device name.

    The format is: <package_version>-<truncated_md5>
    where truncated_md5 is the first 8 characters of the MD5 hash of the device name.

    Args:
        device_name: Name of the device to hash

    Returns:
        Firmware revision string like "0.1.0-a1b2c3d4"
    """
    pkg_version = get_package_version()
    name_hash = hashlib.md5(device_name.encode()).hexdigest()[:8]
    return f"{pkg_version}-{name_hash}"


def get_model_name_for_equipment(equipment: Any) -> str:
    """
    Get the model name based on equipment class type.

    Args:
        equipment: Equipment instance

    Returns:
        Model name string based on equipment type
    """
    class_name = equipment.__class__.__name__
    return EQUIPMENT_MODEL_NAMES.get(class_name, DEFAULT_MODEL_NAME)


@dataclass
class BACnetDeviceConfig:
    """
    Configuration for creating a BACnet device.

    Supports two network modes:
    1. IPv4 BACnet/IP: Set ip_address for real network communication
    2. Virtual Network: Set vlan_name and mac_address for testing

    Attributes:
        device_id: BACnet device instance number (auto-generated if None)
        device_name: BACnet device name
        ip_address: IP address with optional CIDR (e.g., "172.26.0.20/16")
        subnet_mask: Subnet mask (default "255.255.0.0")
        gateway: Default gateway IP
        port: BACnet/IP UDP port (default 47808)
        vlan_name: Virtual LAN name for testing
        mac_address: MAC address for virtual network
        model_name: Model name for device object
        description: Device description
    """

    device_id: Optional[int] = None
    device_name: Optional[str] = None
    ip_address: Optional[str] = None
    subnet_mask: str = "255.255.0.0"
    gateway: str = "172.26.0.1"
    port: int = BACNET_DEFAULT_PORT
    vlan_name: Optional[str] = None
    mac_address: Optional[str] = None
    model_name: str = "HVAC-Simulator"
    description: str = ""

    def is_ip_mode(self) -> bool:
        """Check if configured for IP mode."""
        return self.ip_address is not None

    def is_vlan_mode(self) -> bool:
        """Check if configured for VLAN mode."""
        return self.vlan_name is not None


def _build_device_config(
    equipment: Any, equipment_name: str, config: BACnetDeviceConfig
) -> List[Dict[str, Any]]:
    """
    Build the JSON configuration for a BACnet device.

    Args:
        equipment: Equipment instance (used for determining model name)
        equipment_name: Name of the equipment
        config: Device configuration

    Returns:
        List of configuration dictionaries for Application.from_json()
    """
    # Generate device ID from name if not provided
    device_id = config.device_id
    if device_id is None:
        device_id = hash(equipment_name) % 4000000 + 1000

    device_name = config.device_name or f"Device-{equipment_name}"
    description = config.description or f"Simulated Equipment - {equipment_name}"

    # Get model name from equipment type (unless explicitly configured)
    model_name = config.model_name
    if model_name == "HVAC-Simulator":  # Default value, override with equipment-specific
        model_name = get_model_name_for_equipment(equipment)

    # Generate firmware revision from package version and device name
    firmware_revision = generate_firmware_revision(device_name)

    # Base device configuration
    app_config: List[Dict[str, Any]] = [
        {
            "apdu-segment-timeout": 1000,
            "apdu-timeout": 3000,
            "application-software-version": get_package_version(),
            "database-revision": 1,
            "firmware-revision": firmware_revision,
            "max-apdu-length-accepted": BACNET_MAX_APDU_LENGTH,
            "model-name": model_name,
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
            "description": description,
        }
    ]

    # Add network port configuration
    if config.is_ip_mode():
        ip_addr = config.ip_address
        if ip_addr and "/" in ip_addr:
            ip_addr = ip_addr.split("/")[0]

        app_config.append(
            {
                "changes-pending": False,
                "ip-address": ip_addr,
                "ip-subnet-mask": config.subnet_mask,
                "ip-default-gateway": config.gateway,
                "bacnet-ip-mode": "normal",
                "bacnet-ip-udp-port": config.port,
                "network-type": "ipv4",
                "object-identifier": "network-port,1",
                "object-name": "BACnet-IP-Port",
                "object-type": "network-port",
                "out-of-service": False,
                "protocol-level": "bacnet-application",
                "reliability": "no-fault-detected",
            }
        )
    else:
        # VLAN mode (default for testing)
        vlan_name = config.vlan_name or "vlan"
        mac_address = config.mac_address or "0x01"
        formatted_mac = hex_to_padded_octets(mac_address)

        app_config.append(
            {
                "object-identifier": "network-port,1",
                "object-name": "VirtualPort",
                "object-type": "network-port",
                "network-type": "virtual",
                "network-interface-name": vlan_name,
                "mac-address": formatted_mac,
                "out-of-service": False,
                "protocol-level": "bacnet-application",
                "reliability": "no-fault-detected",
            }
        )

    return app_config


def create_bacnet_device(
    equipment: Any, config: Optional[BACnetDeviceConfig] = None
) -> Optional["Application"]:
    """
    Create a BACnet device for the given equipment.

    This function creates a BACpypes3 Application configured with points
    for all process variables defined by the equipment.

    Args:
        equipment: Equipment instance with get_process_variables() and
                   get_process_variables_metadata() methods
        config: Optional device configuration (uses defaults if None)

    Returns:
        BACpypes3 Application instance, or None if creation failed
    """
    from bacpypes3.app import Application
    from src.bacnet.points import create_bacnet_point

    if config is None:
        config = BACnetDeviceConfig()

    equipment_name = getattr(equipment, "name", "Unknown")

    # Log creation
    if config.is_ip_mode():
        logger.info("Creating BACnet device for %s on IP %s", equipment_name, config.ip_address)
    else:
        logger.info(
            "Creating BACnet device for %s on VLAN %s",
            equipment_name,
            config.vlan_name or "default",
        )

    # Build configuration
    app_config = _build_device_config(equipment, equipment_name, config)

    try:
        # Create the application
        app = Application.from_json(app_config)

        if app:
            device_name = config.device_name or f"Device-{equipment_name}"
            setattr(app, "name", device_name)
    except Exception as e:
        logger.exception("Error creating BACnet device for %s: %s", equipment_name, e)
        return None

    # Get process variables and metadata
    try:
        process_vars = equipment.get_process_variables()
        metadata = equipment.get_process_variables_metadata()
    except AttributeError as e:
        logger.error("Equipment %s missing required methods: %s", equipment_name, e)
        return app

    # Add BACnet points for each process variable
    point_id = 3  # Start at 3 (device=1, network-port=2)

    for point_name, point_meta in metadata.items():
        # Skip certain fields
        if point_name in ("name", "location", "timezone"):
            continue

        # Skip unsupported types
        point_type = point_meta.get("type")
        if point_type not in (float, int, bool, str):
            continue

        # Get current value
        value = process_vars.get(point_name)
        if value is None:
            continue

        # Create and add the point
        point_obj = create_bacnet_point(
            point_id=point_id, point_name=point_name, point_meta=point_meta, value=value
        )

        if point_obj:
            app.add_object(point_obj)
            point_id += 1

    # Store cross-references
    app.sim_device = equipment
    equipment.app = app

    return app
