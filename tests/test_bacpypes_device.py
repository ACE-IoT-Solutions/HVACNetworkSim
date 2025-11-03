import asyncio
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bacpypes3.app import Application
from bacpypes3.vlan import VirtualNetwork
from bacpypes3.object import DeviceObject
from bacpypes3.primitivedata import Real
from bacpypes3.pdu import Address

from src.vav_box import VAVBox


class BACpypesVAVDeviceTests(unittest.IsolatedAsyncioTestCase):
    """Test cases for VAVBox BACpypes3 integration."""

    vlan: VirtualNetwork | None = None

    @classmethod
    def setUpClass(cls):
        cls.vlan = VirtualNetwork("test-vlan")

    @classmethod
    def tearDownClass(cls):
        if cls.vlan:
            # cls.vlan.close()  # Commented out as VirtualNetwork may not have this method
            pass
        cls.vlan = None

    def setUp(self):
        self.vav = VAVBox(
            name="Test-VAV",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=80,
            window_orientation="east",
            thermal_mass=2.0,
        )

    async def async_test_device_creation_and_properties(self):
        device_app: Application | None = None
        try:
            assert self.vlan is not None, "VirtualNetwork not initialized in setUpClass"
            device_app = self.vav.create_bacpypes3_device(
                device_id=1001,
                device_name="VAV-001",
                network_interface_name="test-vlan",
                mac_address="0x01",
            )
            self.assertIsNotNone(device_app, "Failed to create BACpypes device app")
            if not device_app:
                self.fail("device_app is None after creation")
                return

            self.vlan.add_node(device_app) # Reverted to add app directly

            self.assertIsInstance(device_app, Application)
            device_obj = device_app.device_object
            self.assertIsNotNone(device_obj, "Device object not found on application")
            if not device_obj:
                self.fail("device_obj is None")
                return

            self.assertEqual(device_obj.objectIdentifier[1], 1001)
            self.assertEqual(device_obj.objectName, "VAV-001")

            object_list_values = device_app.objectIdentifier.values()
            essential_points = ["zone_temp", "damper_position", "reheat_valve_position", "mode"]

            for point_name in essential_points:
                found = False
                for obj_id in object_list_values:
                    obj = device_app.get_object_id(obj_id)
                    if obj and hasattr(obj, "objectName") and obj.objectName == point_name:
                        found = True
                        break
                self.assertTrue(found, f"Point {point_name} not found in device objects")
        finally:
            if device_app:
                await device_app.close()

    async def async_test_device_value_updates(self):
        device_app: Application | None = None
        try:
            assert self.vlan is not None, "VirtualNetwork not initialized"
            device_app = self.vav.create_bacpypes3_device(
                device_id=1001,
                device_name="VAV-001",
                network_interface_name="test-vlan",
                mac_address="0x01",
            )
            self.assertIsNotNone(device_app, "Failed to create BACpypes device app")
            if not device_app:
                self.fail("device_app is None after creation")
                return

            self.vlan.add_node(device_app) # Reverted to add app directly

            initial_temp = self.vav.zone_temp
            zone_temp_point = device_app.get_object_name("zone_temp")
            self.assertIsNotNone(zone_temp_point, "zone_temp object not found on device")
            if zone_temp_point is None:
                self.fail("zone_temp_point is None")
                return

            new_temp = initial_temp + 5
            self.vav.zone_temp = new_temp
            await self.vav.update_bacnet_device()
            self.assertEqual(zone_temp_point.presentValue, new_temp)
        finally:
            if device_app:
                await device_app.close()

    async def async_test_two_devices_on_network(self):
        device1_app: Application | None = None
        device2_app: Application | None = None
        controller_app: Application | None = None
        controller_name = "Controller"
        try:
            assert self.vlan is not None, "VirtualNetwork not initialized"
            vav2 = VAVBox(
                name="Test-VAV-2",
                min_airflow=100,
                max_airflow=1000,
                zone_temp_setpoint=70,
                deadband=2,
                discharge_air_temp_setpoint=55,
                has_reheat=True,
                zone_area=300,
                zone_volume=2400,
                window_area=60,
                window_orientation="west",
                thermal_mass=1.5,
            )

            device1_app = self.vav.create_bacpypes3_device(
                device_id=1001, device_name="VAV-001", network_interface_name="test-vlan", mac_address="0x01"
            )
            self.assertIsNotNone(device1_app, "Failed to create device1_app")
            if not device1_app:
                self.fail("device1_app is None")
                return
            self.vlan.add_node(device1_app) # Reverted to add app directly

            device2_app = vav2.create_bacpypes3_device(
                device_id=1002, device_name="VAV-002", network_interface_name="test-vlan", mac_address="0x02"
            )
            self.assertIsNotNone(device2_app, "Failed to create device2_app")
            if not device2_app:
                self.fail("device2_app is None")
                return
            self.vlan.add_node(device2_app) # Reverted to add app directly

            controller_device_object = DeviceObject(
                objectIdentifier=("device", 1000), objectName=controller_name, vendorIdentifier=999
            )
            controller_app = Application(controller_device_object, network_interface_name="test-vlan", aseID=None)
            self.assertIsNotNone(controller_app, "Failed to create controller_app")
            if not controller_app:
                self.fail("controller_app is None")
                return
            setattr(controller_app, "name", controller_name)  # Ensure name is set
            self.vlan.add_node(controller_app) # Reverted to add app directly

            await asyncio.sleep(0.2)
            i_ams = await controller_app.who_is()

            device_ids = sorted([i_am.iAmDeviceIdentifier[1] for i_am in i_ams])
            self.assertEqual(device_ids, [1001, 1002])
        finally:
            if device1_app:
                await device1_app.close()
            if device2_app:
                await device2_app.close()
            if controller_app:
                await controller_app.close()

    async def async_test_read_property(self):
        device_app: Application | None = None
        client_app: Application | None = None
        client_name = "Client"
        try:
            assert self.vlan is not None, "VirtualNetwork not initialized"
            device_app = self.vav.create_bacpypes3_device(
                device_id=1001, device_name="VAV-001", network_interface_name="test-vlan", mac_address="0x01"
            )
            self.assertIsNotNone(device_app, "Failed to create device_app")
            if not device_app:
                self.fail("device_app is None")
                return
            # self.vlan.add_node(device_app) # OLD
            device_adapter_node = device_app.adapters[0]
            device_adapter_node.name = device_app.localDevice.objectName # Use localDevice
            self.vlan.add_node(device_adapter_node)

            client_device_object = DeviceObject(
                objectIdentifier=("device", 2000), objectName=client_name, vendorIdentifier=999
            )
            client_app = Application(client_device_object, network_interface_name="test-vlan", aseID=None)
            self.assertIsNotNone(client_app, "Failed to create client_app")
            if not client_app:
                self.fail("client_app is None")
                return
            # setattr(client_app, "name", client_name)  # REMOVED
            # self.vlan.add_node(client_app) # OLD
            client_adapter_node = client_app.adapters[0]
            client_adapter_node.name = client_app.localDevice.objectName # Use localDevice
            self.vlan.add_node(client_adapter_node)

            await asyncio.sleep(0.2)
            i_ams = await client_app.who_is()
            vav_address: Address | None = None
            for i_am in i_ams:
                if i_am.iAmDeviceIdentifier[1] == 1001:
                    vav_address = i_am.pduSource
                    break

            self.assertIsNotNone(vav_address, "VAV device not found on network")
            if vav_address is None:
                self.fail("vav_address is None after who_is check")
                return

            zone_temp_bacnet_object = device_app.get_object_name("zone_temp")
            self.assertIsNotNone(zone_temp_bacnet_object, "BACnet object 'zone_temp' not found on device_app")
            if zone_temp_bacnet_object is None:
                self.fail("zone_temp_bacnet_object is None")
                return

            zone_temp_id_to_read = zone_temp_bacnet_object.objectIdentifier

            result = await client_app.read_property(
                address=vav_address, objid=zone_temp_id_to_read, prop="presentValue"
            )

            self.assertEqual(result, self.vav.zone_temp)
        finally:
            if device_app:
                await device_app.close()
            if client_app:
                await client_app.close()

    async def async_test_write_property(self):
        device_app: Application | None = None
        client_app: Application | None = None
        client_name = "Client"
        try:
            assert self.vlan is not None, "VirtualNetwork not initialized"
            device_app = self.vav.create_bacpypes3_device(
                device_id=1001, device_name="VAV-001", network_interface_name="test-vlan", mac_address="0x01"
            )
            self.assertIsNotNone(device_app, "Failed to create device_app")
            if not device_app:
                self.fail("device_app is None")
                return
            # self.vlan.add_node(device_app) # OLD
            device_adapter_node = device_app.adapters[0]
            device_adapter_node.name = device_app.localDevice.objectName # Use localDevice
            self.vlan.add_node(device_adapter_node)

            client_device_object = DeviceObject(
                objectIdentifier=("device", 2000), objectName=client_name, vendorIdentifier=999
            )
            client_app = Application(client_device_object, network_interface_name="test-vlan", aseID=None)
            self.assertIsNotNone(client_app, "Failed to create client_app")
            if not client_app:
                self.fail("client_app is None")
                return
            # setattr(client_app, "name", client_name)  # REMOVED
            # self.vlan.add_node(client_app) # OLD
            client_adapter_node = client_app.adapters[0]
            client_adapter_node.name = client_app.localDevice.objectName # Use localDevice
            self.vlan.add_node(client_adapter_node)

            await asyncio.sleep(0.2)
            i_ams = await client_app.who_is()
            vav_address: Address | None = None
            for i_am in i_ams:
                if i_am.iAmDeviceIdentifier[1] == 1001:
                    vav_address = i_am.pduSource
                    break

            self.assertIsNotNone(vav_address, "VAV device not found on network")
            if vav_address is None:
                self.fail("vav_address is None after who_is check")
                return

            setpoint_bacnet_object = device_app.get_object_name("zone_temp_setpoint")
            self.assertIsNotNone(setpoint_bacnet_object, "BACnet object 'zone_temp_setpoint' not found on device_app")
            if setpoint_bacnet_object is None:
                self.fail("setpoint_bacnet_object is None")
                return

            setpoint_id_to_write = setpoint_bacnet_object.objectIdentifier
            new_setpoint = 75.0
            await client_app.write_property(
                address=vav_address, objid=setpoint_id_to_write, prop="presentValue", value=Real(new_setpoint)
            )
            await asyncio.sleep(0.1)
            self.assertEqual(setpoint_bacnet_object.presentValue, new_setpoint)
        finally:
            if device_app:
                await device_app.close()
            if client_app:
                await client_app.close()

    def test_async_device_creation_and_properties(self):
        asyncio.run(self.async_test_device_creation_and_properties())

    def test_async_device_value_updates(self):
        asyncio.run(self.async_test_device_value_updates())

    def test_async_two_devices_on_network(self):
        asyncio.run(self.async_test_two_devices_on_network())

    def test_async_read_property(self):
        asyncio.run(self.async_test_read_property())

    def test_async_write_property(self):
        asyncio.run(self.async_test_write_property())


if __name__ == "__main__":
    unittest.main() # Ensure unittest.main() is called correctly