import asyncio
import logging

from bacpypes3.app import Application
from bacpypes3.object import (
    AnalogValueObject,
    BinaryValueObject,
    MultiStateValueObject,
    CharacterStringValueObject,
)

logger = logging.getLogger(__name__)


def hex_to_padded_octets(hex_string):
    """Converts a hex string to a list of padded octets."""
    hex_string = hex_string.replace("0x", "")  # Remove any "0x" prefixes
    if len(hex_string) % 2 != 0:
        hex_string = "0" + hex_string  # Pad with a leading zero if necessary
    return "0x" + "".join([hex_string[i : i + 2] for i in range(0, len(hex_string), 2)])


class BACPypesApplicationMixin:
    async def update_bacnet_device(self):
        """
        Update a BACnet device with current device state.

        Args:
            app: BACpypes3 Application object with device_object reference
        """

        # device_obj = app.device_object

        try:
            # Get updated process variables
            process_vars = self.get_process_variables()

            # Track number of updated points
            update_count = 0

            # For each object in the application
            for obj in self.app.objectIdentifier.values():
                try:
                    # Skip if not a point object with objectName
                    if not hasattr(obj, "objectName"):
                        continue

                    point_name: str = obj.objectName

                    # Skip if this is not one of our process variables
                    if point_name not in process_vars:
                        continue

                    value = process_vars[point_name]

                    # Skip complex types
                    if isinstance(value, (dict, list, tuple)) or value is None:
                        continue

                    # Handle different object types appropriately
                    if hasattr(obj, "objectType"):
                        obj_type = obj.objectType

                        # For multi-state values, convert string to index
                        if obj_type == "multi-state-value" and hasattr(obj, "stateText"):
                            state_text = obj.stateText
                            if value in state_text:
                                # 1-based index for BACnet MSV
                                idx = state_text.index(value) + 1
                                # Only update if changed, to reduce network traffic
                                if obj.presentValue != idx:
                                    obj.presentValue = idx
                                    update_count += 1
                                continue

                        # For analog values, ensure float
                        elif obj_type == "analog-value" and isinstance(value, (int, float)):
                            # Check if value has changed before updating
                            # Use a small epsilon for floating point comparison
                            if abs(obj.presentValue - float(value)) > 0.001:
                                obj.presentValue = float(value)
                                update_count += 1
                            continue

                        # For binary values, ensure boolean
                        elif obj_type == "binary-value" and isinstance(value, bool):
                            if obj.presentValue != bool(value):
                                obj.presentValue = bool(value)
                                update_count += 1
                            continue

                        # For string properties represented as analog values
                        elif (
                            obj_type == "analog-value"
                            and obj.description
                            and "string length" in obj.description
                        ):
                            str_len = float(len(str(value)))
                            if obj.presentValue != str_len:
                                obj.presentValue = str_len
                                update_count += 1
                            continue

                    # Fallback for direct assignment - only attempt if necessary
                    try:
                        # Need to check if the value is already equal
                        # This is a simplistic check that might not work for all types
                        if hasattr(obj, "presentValue") and obj.presentValue != value:
                            obj.presentValue = value
                            update_count += 1
                    except Exception as e:
                        logger.debug("Could not directly assign value to %s: %s", point_name, e)
                except Exception as e:
                    logger.warning(
                        "Error updating point %s: %s", getattr(obj, "objectName", "unknown"), e
                    )

            # Only log if we actually updated something, to reduce console spam
            if update_count > 0:
                logger.debug("Updated %d BACnet points for %s", update_count, self.name)

        except Exception as e:
            logger.error("Error updating BACnet device %s: %s", self.name, e)

        # Add a small delay to avoid overwhelming the BACnet stack
        await asyncio.sleep(0.05)

    def create_bacpypes3_device(
        self,
        device_id=None,
        device_name=None,
        ip_address=None,
        network_interface_name=None,
        mac_address=None,
    ):
        """
        Create a BACpypes3 device representation of this VAV box.

        Supports two modes:
        1. IPv4 BACnet/IP mode: Provide ip_address for real network communication
        2. Virtual Network mode: Provide network_interface_name and mac_address for testing

        Args:
            device_id: BACnet device ID (defaults to a hash of the VAV name)
            device_name: BACnet device name (defaults to VAV name)
            ip_address: IP address with CIDR notation (e.g., "172.26.0.20/16") for BACnet/IP mode
            network_interface_name: Name of the virtual network for testing mode
            mac_address: MAC address for virtual network testing mode

        Returns:
            BACpypes3 Application object
        """
        # Set default device ID and name if not provided
        if device_id is None:
            # Generate a hash from the name
            device_id = hash(self.name) % 4000000 + 1000  # Ensure positive ID

        if device_name is None:
            device_name = f"VAV-{self.name}"

        # Determine which mode to use
        use_ip_mode = ip_address is not None
        use_vlan_mode = network_interface_name is not None

        if use_ip_mode:
            logger.info("Creating %s with ID %d on IP %s", device_name, device_id, ip_address)
        elif use_vlan_mode:
            logger.info(
                "Creating %s with ID %d on VLAN %s", device_name, device_id, network_interface_name
            )
        else:
            # Default to VLAN mode for backwards compatibility with tests
            network_interface_name = "vlan"
            mac_address = "0x01" if mac_address is None else mac_address
            use_vlan_mode = True
            logger.info("Creating %s with ID %d on default VLAN", device_name, device_id)

        # Create JSON-compatible configuration list for the application
        app_config = [
            # Device Object
            {
                "apdu-segment-timeout": 1000,
                "apdu-timeout": 3000,
                "application-software-version": "1.0",
                "database-revision": 1,
                "firmware-revision": "N/A",
                "max-apdu-length-accepted": 1024,
                "model-name": "VAV-Simulator",
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
                "description": f"Simulated VAV Box - {self.name}",
            }
        ]

        # Add network port configuration based on mode
        if use_ip_mode:
            # IPv4 BACnet/IP mode for real network communication
            app_config.append(
                {
                    "changes-pending": False,
                    "ip-address": ip_address.split("/")[0],  # Extract IP without CIDR
                    "ip-subnet-mask": "255.255.0.0",  # For /16 subnet
                    "ip-default-gateway": "172.26.0.1",
                    "bacnet-ip-mode": "normal",  # Normal BACnet/IP mode
                    "bacnet-ip-udp-port": 47808,
                    "network-type": "ipv4",
                    "object-identifier": "network-port,1",
                    "object-name": "BACnet-IP-Port",
                    "object-type": "network-port",
                    "out-of-service": False,
                    "protocol-level": "bacnet-application",
                    "reliability": "no-fault-detected",
                }
            )
        elif use_vlan_mode:
            # Virtual network mode - let BACpypes3 connect to existing VLAN
            # Ensure MAC address is properly formatted (even length hex)
            formatted_mac = mac_address if mac_address else "0x01"
            formatted_mac = hex_to_padded_octets(formatted_mac)

            app_config.append(
                {
                    "object-identifier": "network-port,1",
                    "object-name": "VirtualPort",
                    "object-type": "network-port",
                    "network-type": "virtual",
                    "network-interface-name": network_interface_name,
                    "mac-address": formatted_mac,
                    "out-of-service": False,
                    "protocol-level": "bacnet-application",
                    "reliability": "no-fault-detected",
                }
            )

        try:
            # Create the application using from_json method
            app = Application.from_json(app_config)

            if app and device_name:
                setattr(app, "name", device_name)
        except Exception as e:
            logger.exception("Error creating BACnet device %s: %s", device_name, e)
            return None

        # Add data points to the application config
        point_id = 3  # Start at ID 3 since 1 and 2 are used by device and network-port

        # Get current values
        process_vars = self.get_process_variables()
        metadata = self.get_process_variables_metadata()

        # Create and add objects for each variable
        for point_name, point_meta in metadata.items():
            # Skip complex types
            if point_meta["type"] not in (float, int, bool, str):
                continue
            if point_name in ("name", "location", "timezone"):
                continue
            # print(f"Adding {point_name} ({point_meta['label']})")

            # Get current value
            value = process_vars.get(point_name)
            if value is None:
                continue

            # Create appropriate object config based on type
            if point_meta["type"] in (float, int):
                # Get units
                units = "no-units"
                if "unit" in point_meta:
                    # Direct unit conversion
                    unit_text = point_meta["unit"]
                    if unit_text in ("°F", "degF"):
                        units = "degrees-fahrenheit"
                    elif unit_text in ("CFM", "ft³/min"):
                        units = "cubic-feet-per-minute"
                    elif unit_text == "fraction":
                        units = "percent"
                    elif unit_text == "sq ft":
                        units = "square-feet"
                    elif unit_text == "cu ft":
                        units = "cubic-feet"

                # Create analog value object

                point_obj = AnalogValueObject(
                    objectIdentifier=f"analog-value,{point_id}",
                    objectName=point_name,
                    description=point_meta["label"],
                    presentValue=float(value),
                    units=units,
                )

            elif point_meta["type"] is bool:
                # Create binary value object
                point_obj = BinaryValueObject(
                    objectIdentifier=f"binary-value,{point_id}",
                    objectName=point_name,
                    description=point_meta["label"],
                    presentValue=bool(value),
                )
            elif point_meta["type"] is str and "options" in point_meta:
                point_obj = MultiStateValueObject(
                    objectIdentifier=f"multi-state-value,{point_id}",
                    objectName=point_name,
                    description=point_meta["label"],
                    presentValue=point_meta["options"].index(value) + 1,
                    numberOfStates=len(point_meta["options"]),
                    stateText=point_meta["options"],
                )
            else:
                point_obj = CharacterStringValueObject(
                    objectIdentifier=f"character-string-value,{point_id}",
                    objectName=point_name,
                    description=point_meta["label"],
                    presentValue=str(value),
                )
            app.add_object(point_obj)
            point_id += 1

        # Store a reference to the VAV box in the app for updates
        app.sim_device = self
        self.app = app

        # In BACpypes3, the Application is already running when created
        # No explicit startup() call needed

        # Return the application
        return app
