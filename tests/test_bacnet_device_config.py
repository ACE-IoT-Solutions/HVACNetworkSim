"""Tests for BACnet device network-port configuration."""

import unittest

from src.bacnet.device import BACnetDeviceConfig, _build_device_config


class _DummyEquipment:
    pass


class TestBACnetDeviceConfig(unittest.TestCase):
    """Verify IP-mode metadata matches the configured BACnet network."""

    def test_ip_mode_derives_subnet_gateway_and_network_number(self):
        config = BACnetDeviceConfig(
            device_id=100,
            device_name="Device-Test",
            ip_address="10.12.0.10/24",
            port=47809,
            network_number=200,
        )

        app_config = _build_device_config(_DummyEquipment(), "Test", config)
        port_config = next(
            entry for entry in app_config if entry.get("object-type") == "network-port"
        )

        self.assertEqual(port_config["ip-address"], "10.12.0.10")
        self.assertEqual(port_config["ip-subnet-mask"], "255.255.255.0")
        self.assertEqual(port_config["ip-default-gateway"], "10.12.0.1")
        self.assertEqual(port_config["bacnet-ip-udp-port"], 47809)
        self.assertEqual(port_config["network-number"], 200)
        self.assertEqual(port_config["network-number-quality"], "configured")


if __name__ == "__main__":
    unittest.main()
