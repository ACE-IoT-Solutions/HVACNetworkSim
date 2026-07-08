"""Focused tests for env-driven runtime wiring in src.main."""

import asyncio
import os
import unittest
from unittest.mock import patch

from src import main


class _FakePoint:
    def __init__(self, name: str, value, object_type: str):
        self.objectName = name
        self.presentValue = value
        self.objectType = object_type


class _FakeDeviceObject:
    objectName = "VAV-Office-1"
    objectIdentifier = ("device", 100)


class _FakeDevice:
    def __init__(self):
        self.device_object = _FakeDeviceObject()
        self.objectIdentifier = {
            1: _FakePoint("zone_temp", 72.0, "analog-value"),
            2: _FakePoint("damper_position", 0.0, "analog-value"),
            3: _FakePoint("reheat_valve_position", 0.0, "analog-value"),
            4: _FakePoint("mode", 1, "multi-state-value"),
        }


class _FakeVAVBox:
    last_create_kwargs = None

    def __init__(self, *args, **kwargs):
        self.zone_temp = 72.0
        self.mode = "deadband"
        self.has_reheat = True
        self.current_airflow = 100.0
        self.max_airflow = 1000.0
        self.reheat_valve_position = 0.0

    def set_occupancy(self, occupancy_count: int):
        self.occupancy_count = occupancy_count

    def update(self, zone_temp: float, supply_air_temp: float):
        self.zone_temp = zone_temp

    def calculate_thermal_behavior(self, **kwargs) -> float:
        return 0.0

    def create_bacpypes3_device(self, **kwargs):
        type(self).last_create_kwargs = kwargs
        return _FakeDevice()

    async def update_bacnet_device(self):
        raise asyncio.CancelledError


class _FakeCampusVAVBox:
    def __init__(self, name: str, *args, **kwargs):
        self.name = name
        self.zone_temp = 72.0
        self.mode = "deadband"
        self.has_reheat = True
        self.reheat_valve_position = 0.0
        self.current_airflow = 100.0
        self.max_airflow = 1000.0

    def set_occupancy(self, occupancy_count: int):
        self.occupancy_count = occupancy_count

    def update(self, *args, **kwargs):
        return None

    def calculate_thermal_behavior(self, **kwargs) -> float:
        return 0.0

    async def update_bacnet_device(self):
        return None


class _FakeCampusAHU:
    def __init__(self, name: str, *args, **kwargs):
        self.name = name

    def update(self, *args, **kwargs):
        return None

    async def update_bacnet_device(self):
        return None


class _FakeCampusNetworkInfo:
    def __init__(self, name: str, network_number: int):
        self.name = name
        self.network_number = network_number
        self.devices = []


class _FakeCampusNetworkManager:
    BUILDING_DEVICE_ID_RANGE = 1000
    BUILDING_NETWORK_RANGE = 1000
    last_router_kwargs = None
    added_devices = []

    def __init__(self, *args, **kwargs):
        self.networks = {1100: _FakeCampusNetworkInfo("ahu-ahu01", 1100)}

    def create_ip_to_vlan_router(self, **kwargs):
        type(self).last_router_kwargs = kwargs
        return object()

    def get_network_for_ahu(self, ahu_name: str):
        return self.networks[1100]

    def add_device_to_network(self, equipment, network_info, device_id=None, device_name=None):
        type(self).added_devices.append((device_name, device_id, network_info.network_number))
        return object()

    def get_central_plant_network(self):
        return None

    def print_network_topology(self):
        return None

    def print_device_table(self, bacnet_address=None):
        return None

    def get_network_summary(self):
        return {"total_networks": 1, "total_devices": len(type(self).added_devices)}


class TestMainSimpleSimulation(unittest.IsolatedAsyncioTestCase):
    """Verify simple mode applies validated BACnet env settings."""

    async def test_run_simple_simulation_passes_runtime_network_settings(self):
        _FakeVAVBox.last_create_kwargs = None
        with patch.dict(
            os.environ,
            {
                "BACNET_ADDRESS": "10.11.0.10/24",
                "BACNET_PORT": "47809",
                "BACNET_DEVICE_ID": "100",
                "BACNET_NETWORK_NUMBER": "200",
            },
            clear=False,
        ):
            with patch.object(main, "VAVBox", _FakeVAVBox):
                await main.run_simple_simulation()

        self.assertEqual(
            _FakeVAVBox.last_create_kwargs,
            {
                "device_id": 100,
                "ip_address": "10.11.0.10/24",
                "bacnet_port": 47809,
                "network_number": 200,
            },
        )

    async def test_run_brick_simulation_uses_router_network_number_and_ttl_device_ids(self):
        async def cancel_gather(*args, **kwargs):
            for task in args:
                await task
            raise asyncio.CancelledError

        _FakeCampusNetworkManager.last_router_kwargs = None
        _FakeCampusNetworkManager.added_devices = []
        building_structure = {
            "building": {"name": "Building1"},
            "ahus": {"AHU01": {"id": "AHU01", "device_id": 101}},
            "vavs": {"VAV01": {"id": "VAV01", "device_id": 100}},
            "zones": {},
            "chillers": {},
            "boilers": {},
        }

        with patch.dict(
            os.environ,
            {
                "BACNET_ADDRESS": "10.1.0.10/24",
                "BACNET_NETWORK_NUMBER": "200",
                "ROUTER_CLAIMED_NETWORKS": "2100,2200",
            },
            clear=False,
        ):
            with (
                patch.object(main, "BACnetNetworkManager", _FakeCampusNetworkManager),
                patch.object(
                    main, "create_building_networks_from_brick", lambda *args, **kwargs: None
                ),
                patch.object(main, "get_vav_network_assignment", lambda *args, **kwargs: "AHU01"),
                patch.object(main, "VAVBox", _FakeCampusVAVBox),
                patch.object(main, "AirHandlingUnit", _FakeCampusAHU),
                patch.object(main.asyncio, "gather", cancel_gather),
            ):
                await main.run_brick_simulation(
                    building_structure=building_structure,
                    device_id_start=1000,
                    network_number_base=1000,
                )

        self.assertEqual(
            _FakeCampusNetworkManager.last_router_kwargs["ip_network_number"],
            200,
        )
        self.assertEqual(
            _FakeCampusNetworkManager.last_router_kwargs["claimed_network_numbers"],
            [2100, 2200],
        )
        self.assertIn(("VAV-VAV01", 100, 1100), _FakeCampusNetworkManager.added_devices)
        self.assertIn(("AHU-AHU01", 101, 1100), _FakeCampusNetworkManager.added_devices)


if __name__ == "__main__":
    unittest.main()
