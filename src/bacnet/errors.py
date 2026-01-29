"""BACnet error injection and validation for testing and training.

This module provides tools for:
1. Injecting common BACnet configuration errors (duplicate IDs, networks, routers)
2. Validating BACnet network configurations to detect these errors
3. Generating reports of detected errors

Error Types Supported:
- Duplicate Device IDs: Multiple devices with the same device instance number
- Duplicate Network Numbers: Multiple networks with the same network number
- Duplicate Routers: Multiple routers claiming to route to the same network

These error injection capabilities are useful for:
- Training BACnet technicians to identify and troubleshoot common issues
- Testing BACnet discovery and diagnostic tools
- Simulating real-world misconfiguration scenarios
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.bacnet.device import (
    get_package_version,
    generate_firmware_revision,
)
from src.core.constants import (
    BACNET_VENDOR_ID,
    BACNET_VENDOR_NAME,
    BACNET_MAX_APDU_LENGTH,
    BACNET_PROTOCOL_VERSION,
    BACNET_PROTOCOL_REVISION,
)

logger = logging.getLogger(__name__)

try:
    from bacpypes3.app import Application
    from bacpypes3.vlan import VirtualNetwork

    BACPYPES_AVAILABLE = True
except ImportError:
    BACPYPES_AVAILABLE = False
    Application = None  # type: ignore
    VirtualNetwork = None  # type: ignore


@dataclass
class ErrorInjectionConfig:
    """Configuration for error injection.

    Attributes:
        duplicate_device_ids: List of (device_id, count) tuples to create duplicates
        duplicate_network_numbers: List of (network_number, count) tuples
        duplicate_routers: List of network numbers to add duplicate routers to
        random_seed: Optional seed for reproducible random selections
    """

    duplicate_device_ids: List[Tuple[int, int]] = field(default_factory=list)
    duplicate_network_numbers: List[Tuple[int, int]] = field(default_factory=list)
    duplicate_routers: List[int] = field(default_factory=list)
    random_seed: Optional[int] = None

    def has_errors(self) -> bool:
        """Check if any errors are configured."""
        return bool(
            self.duplicate_device_ids or self.duplicate_network_numbers or self.duplicate_routers
        )


@dataclass
class DetectedError:
    """A detected BACnet configuration error.

    Attributes:
        error_type: Type of error (duplicate_device_id, duplicate_network, duplicate_router)
        identifier: The duplicate identifier (device ID, network number, etc.)
        locations: List of locations where the duplicate was found
        severity: Error severity (error, warning)
        description: Human-readable description
    """

    error_type: str
    identifier: int
    locations: List[str]
    severity: str = "error"
    description: str = ""


class BACnetErrorInjector:
    """Injects BACnet configuration errors for testing.

    This class creates deliberate configuration errors to simulate
    real-world misconfiguration scenarios.
    """

    # Error device IDs start at 8000 to avoid conflicts
    ERROR_DEVICE_BASE_ID = 8000

    def __init__(self, config: Optional[ErrorInjectionConfig] = None):
        """Initialize the error injector.

        Args:
            config: Optional error injection configuration
        """
        if not BACPYPES_AVAILABLE:
            raise ImportError("BACpypes3 is required for error injection")

        self.config = config or ErrorInjectionConfig()
        self.injected_devices: List[Any] = []
        self.injected_networks: Dict[int, Any] = {}
        self._next_error_id = self.ERROR_DEVICE_BASE_ID

        if self.config.random_seed is not None:
            random.seed(self.config.random_seed)

    def _get_next_error_device_id(self) -> int:
        """Get the next available error device ID."""
        device_id = self._next_error_id
        self._next_error_id += 1
        return device_id

    def inject_duplicate_device_id(
        self,
        device_id: int,
        network_info: Any,
        device_name: Optional[str] = None,
    ) -> Optional[Any]:
        """Create a device with a duplicate device ID.

        Args:
            device_id: The device ID to duplicate
            network_info: NetworkInfo to add the device to
            device_name: Optional name for the duplicate device

        Returns:
            BACpypes3 Application for the duplicate device, or None if failed
        """
        if device_name is None:
            device_name = f"DuplicateDevice-{device_id}"

        logger.warning(f"Injecting duplicate device ID {device_id} as {device_name}")

        # Build minimal device configuration
        device_config = [
            {
                "apdu-segment-timeout": 1000,
                "apdu-timeout": 3000,
                "application-software-version": get_package_version(),
                "database-revision": 1,
                "firmware-revision": generate_firmware_revision(device_name),
                "max-apdu-length-accepted": BACNET_MAX_APDU_LENGTH,
                "model-name": "ACE-ERR-9000",
                "number-of-apdu-retries": 3,
                "object-identifier": f"device,{device_id}",  # Duplicate ID!
                "object-name": device_name,
                "object-type": "device",
                "protocol-revision": BACNET_PROTOCOL_REVISION,
                "protocol-version": BACNET_PROTOCOL_VERSION,
                "segmentation-supported": "segmented-both",
                "system-status": "operational",
                "vendor-identifier": BACNET_VENDOR_ID,
                "vendor-name": BACNET_VENDOR_NAME,
                "description": f"ERROR: Duplicate device ID {device_id}",
            },
            {
                "object-identifier": "network-port,1",
                "object-name": "VirtualPort",
                "object-type": "network-port",
                "network-type": "virtual",
                "network-interface-name": network_info.name,
                "mac-address": f"0x{random.randint(0x10, 0xFF):02x}",
                "out-of-service": False,
                "protocol-level": "bacnet-application",
                "reliability": "no-fault-detected",
            },
        ]

        try:
            app = Application.from_json(device_config)
            app.name = device_name
            app.is_error_device = True
            app.error_type = "duplicate_device_id"

            network_info.devices.append(app)
            self.injected_devices.append(app)

            return app

        except Exception as e:
            logger.exception(f"Error injecting duplicate device: {e}")
            return None

    def inject_duplicate_network_number(
        self,
        network_number: int,
        network_name: Optional[str] = None,
    ) -> Optional[Any]:
        """Create a network with a duplicate network number.

        Args:
            network_number: The network number to duplicate
            network_name: Optional name for the duplicate network

        Returns:
            NetworkInfo-like object for the duplicate network, or None if failed
        """
        if network_name is None:
            network_name = f"duplicate-net-{network_number}"

        logger.warning(f"Injecting duplicate network number {network_number}")

        try:
            vlan = VirtualNetwork(network_name)

            # Create a simple container for network info
            class DuplicateNetworkInfo:
                def __init__(self, num, name, net):
                    self.network_number = num
                    self.name = name
                    self.network = net
                    self.devices = []
                    self.is_error_network = True
                    self.error_type = "duplicate_network_number"

            network_info = DuplicateNetworkInfo(network_number, network_name, vlan)
            self.injected_networks[id(network_info)] = network_info

            return network_info

        except Exception as e:
            logger.exception(f"Error injecting duplicate network: {e}")
            return None

    def inject_duplicate_router(
        self,
        network_number: int,
        network_info: Any,
        router_name: Optional[str] = None,
    ) -> Optional[Any]:
        """Create a duplicate router for a network.

        Args:
            network_number: The network number to add a duplicate router for
            network_info: NetworkInfo to add the router to
            router_name: Optional name for the duplicate router

        Returns:
            BACpypes3 Application for the duplicate router, or None if failed
        """
        device_id = self._get_next_error_device_id()

        if router_name is None:
            router_name = f"DuplicateRouter-Net{network_number}"

        logger.warning(f"Injecting duplicate router for network {network_number}")

        # Build router configuration
        router_config = [
            {
                "apdu-segment-timeout": 1000,
                "apdu-timeout": 3000,
                "application-software-version": get_package_version(),
                "database-revision": 1,
                "firmware-revision": generate_firmware_revision(router_name),
                "max-apdu-length-accepted": BACNET_MAX_APDU_LENGTH,
                "model-name": "ACE-ERR-RTR",
                "number-of-apdu-retries": 3,
                "object-identifier": f"device,{device_id}",
                "object-name": router_name,
                "object-type": "device",
                "protocol-revision": BACNET_PROTOCOL_REVISION,
                "protocol-version": BACNET_PROTOCOL_VERSION,
                "segmentation-supported": "segmented-both",
                "system-status": "operational",
                "vendor-identifier": BACNET_VENDOR_ID,
                "vendor-name": BACNET_VENDOR_NAME,
                "description": f"ERROR: Duplicate router for network {network_number}",
            },
            # Virtual port claiming to route to the target network
            {
                "changes-pending": False,
                "mac-address": "0x01",  # Same as legitimate router!
                "network-interface-name": network_info.name,
                "network-number": network_number,
                "network-number-quality": "configured",
                "network-type": "virtual",
                "object-identifier": "network-port,1",
                "object-name": f"VLAN-{network_info.name}",
                "object-type": "network-port",
                "out-of-service": False,
                "protocol-level": "bacnet-application",
                "reliability": "no-fault-detected",
            },
        ]

        try:
            app = Application.from_json(router_config)
            app.name = router_name
            app.is_error_device = True
            app.error_type = "duplicate_router"

            network_info.devices.append(app)
            self.injected_devices.append(app)

            return app

        except Exception as e:
            logger.exception(f"Error injecting duplicate router: {e}")
            return None

    def apply_errors_to_network(
        self,
        network_manager: Any,
    ) -> List[Any]:
        """Apply configured errors to an existing network.

        Args:
            network_manager: BACnetNetworkManager with existing networks

        Returns:
            List of created error devices/networks
        """
        created = []

        # Inject duplicate device IDs
        for device_id, count in self.config.duplicate_device_ids:
            # Pick random networks to add duplicates to
            networks = list(network_manager.networks.values())
            if networks:
                for _ in range(count):
                    network = random.choice(networks)
                    device = self.inject_duplicate_device_id(device_id, network)
                    if device:
                        created.append(device)

        # Inject duplicate network numbers
        for network_number, count in self.config.duplicate_network_numbers:
            for i in range(count):
                network = self.inject_duplicate_network_number(
                    network_number, f"duplicate-{network_number}-{i}"
                )
                if network:
                    created.append(network)

        # Inject duplicate routers
        for network_number in self.config.duplicate_routers:
            if network_number in network_manager.networks:
                network = network_manager.networks[network_number]
                router = self.inject_duplicate_router(network_number, network)
                if router:
                    created.append(router)

        return created

    def get_injected_errors_summary(self) -> Dict[str, Any]:
        """Get a summary of injected errors."""
        return {
            "duplicate_devices": len(
                [
                    d
                    for d in self.injected_devices
                    if getattr(d, "error_type", "") == "duplicate_device_id"
                ]
            ),
            "duplicate_routers": len(
                [
                    d
                    for d in self.injected_devices
                    if getattr(d, "error_type", "") == "duplicate_router"
                ]
            ),
            "duplicate_networks": len(self.injected_networks),
            "total_error_devices": len(self.injected_devices),
        }


class BACnetValidator:
    """Validates BACnet network configurations and detects errors.

    This class scans a BACnet network configuration and reports
    any detected configuration errors.
    """

    def __init__(self):
        """Initialize the validator."""
        self.errors: List[DetectedError] = []

    def validate_network_manager(self, network_manager: Any) -> List[DetectedError]:
        """Validate a BACnetNetworkManager configuration.

        Args:
            network_manager: BACnetNetworkManager to validate

        Returns:
            List of detected errors
        """
        self.errors = []

        self._check_duplicate_device_ids(network_manager)
        self._check_duplicate_network_numbers(network_manager)
        self._check_duplicate_routers(network_manager)

        return self.errors

    def _check_duplicate_device_ids(self, network_manager: Any) -> None:
        """Check for duplicate device IDs."""
        device_ids: Dict[int, List[str]] = {}

        for network_info in network_manager.networks.values():
            for device in network_info.devices:
                try:
                    device_id = device.device_object.objectIdentifier[1]
                    device_name = getattr(device, "name", f"Device-{device_id}")
                    location = f"{network_info.name}:{device_name}"

                    if device_id not in device_ids:
                        device_ids[device_id] = []
                    device_ids[device_id].append(location)
                except (AttributeError, IndexError):
                    pass

        # Report duplicates
        for device_id, locations in device_ids.items():
            if len(locations) > 1:
                self.errors.append(
                    DetectedError(
                        error_type="duplicate_device_id",
                        identifier=device_id,
                        locations=locations,
                        severity="error",
                        description=f"Device ID {device_id} is used by {len(locations)} devices",
                    )
                )

    def _check_duplicate_network_numbers(self, network_manager: Any) -> None:
        """Check for duplicate network numbers."""
        network_numbers: Dict[int, List[str]] = {}

        for network_info in network_manager.networks.values():
            net_num = network_info.network_number
            if net_num not in network_numbers:
                network_numbers[net_num] = []
            network_numbers[net_num].append(network_info.name)

        # Report duplicates
        for net_num, locations in network_numbers.items():
            if len(locations) > 1:
                self.errors.append(
                    DetectedError(
                        error_type="duplicate_network_number",
                        identifier=net_num,
                        locations=locations,
                        severity="error",
                        description=f"Network number {net_num} is used by {len(locations)} networks",
                    )
                )

    def _check_duplicate_routers(self, network_manager: Any) -> None:
        """Check for duplicate routers on networks."""
        # This would require deeper inspection of router configurations
        # For now, check if multiple devices claim MAC 0x01 on the same network
        for network_info in network_manager.networks.values():
            router_macs: Dict[str, List[str]] = {}

            for device in network_info.devices:
                # Check if device looks like a router (has 0x01 MAC)
                if hasattr(device, "error_type") and device.error_type == "duplicate_router":
                    mac = "0x01"
                    device_name = getattr(device, "name", "Unknown")
                    if mac not in router_macs:
                        router_macs[mac] = []
                    router_macs[mac].append(device_name)

            # Report duplicate routers
            for mac, locations in router_macs.items():
                if len(locations) > 1:
                    self.errors.append(
                        DetectedError(
                            error_type="duplicate_router",
                            identifier=network_info.network_number,
                            locations=locations,
                            severity="error",
                            description=f"Multiple routers on network {network_info.network_number}",
                        )
                    )

    def generate_report(self) -> str:
        """Generate a human-readable error report.

        Returns:
            Formatted error report string
        """
        if not self.errors:
            return "No BACnet configuration errors detected."

        lines = [
            "=" * 60,
            "BACnet Configuration Error Report",
            "=" * 60,
            f"Total errors detected: {len(self.errors)}",
            "",
        ]

        # Group errors by type
        errors_by_type: Dict[str, List[DetectedError]] = {}
        for error in self.errors:
            if error.error_type not in errors_by_type:
                errors_by_type[error.error_type] = []
            errors_by_type[error.error_type].append(error)

        for error_type, errors in errors_by_type.items():
            lines.append(f"\n{error_type.upper().replace('_', ' ')} ({len(errors)} found):")
            lines.append("-" * 40)

            for error in errors:
                lines.append(f"  Identifier: {error.identifier}")
                lines.append(f"  Locations: {', '.join(error.locations)}")
                lines.append(f"  Description: {error.description}")
                lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def has_errors(self) -> bool:
        """Check if any errors were detected."""
        return len(self.errors) > 0

    def get_error_count(self) -> int:
        """Get the total number of detected errors."""
        return len(self.errors)

    def get_errors_by_type(self, error_type: str) -> List[DetectedError]:
        """Get errors of a specific type.

        Args:
            error_type: Type of error to filter by

        Returns:
            List of errors matching the type
        """
        return [e for e in self.errors if e.error_type == error_type]
