#!/usr/bin/env python3
"""
This script provides helper functions for creating BACnet device configurations
that are compatible with BACpypes3.
"""

def create_device_config(device_id, device_name):
    """Create a basic device configuration."""
    # Make sure device_id is an integer
    device_id = int(device_id)
    return {
        "object-identifier": ["device", device_id],
        "object-name": device_name,
        "object-type": "device",
        "vendor-identifier": 999,
        "vendor-name": "HVACNetwork",
        "model-name": "VAVBox",
        "protocol-version": 1,
        "protocol-revision": 19,
        "application-software-version": "1.0",
        "description": f"Virtual VAV Box - {device_name}"
    }

def create_virtual_network_port(network_name, mac_address):
    """Create a virtual network port configuration."""
    return {
        "object-identifier": ["network-port", 1],
        "object-name": "VirtualPort",
        "object-type": "network-port",
        "network-type": "virtual",
        "network-interface-name": network_name,
        "mac-address": mac_address
    }

def create_analog_value(object_id, name, description, initial_value=0.0, units="no-units"):
    """Create an analog value object configuration."""
    return {
        "object-identifier": ["analog-value", object_id],
        "object-name": name,
        "object-type": "analog-value",
        "present-value": float(initial_value),
        "description": description,
        "units": units
    }

def create_binary_value(object_id, name, description, initial_value=False):
    """Create a binary value object configuration."""
    return {
        "object-identifier": ["binary-value", object_id],
        "object-name": name,
        "object-type": "binary-value",
        "present-value": bool(initial_value),
        "description": description
    }

def create_multi_state_value(object_id, name, description, states, initial_state=1):
    """Create a multi-state value object configuration."""
    return {
        "object-identifier": ["multi-state-value", object_id],
        "object-name": name,
        "object-type": "multi-state-value",
        "number-of-states": len(states),
        "state-text": states,
        "present-value": initial_state,
        "description": description
    }

# Unit conversion helpers
def convert_unit_text(unit_text):
    """Convert human-readable unit text to BACnet enumeration values."""
    units_map = {
        "°F": "degrees-fahrenheit",
        "degF": "degrees-fahrenheit",
        "CFM": "cubic-feet-per-minute",
        "ft³/min": "cubic-feet-per-minute",
        "fraction": "percent",
        "sq ft": "square-feet",
        "cu ft": "cubic-feet",
    }
    return units_map.get(unit_text, "no-units")