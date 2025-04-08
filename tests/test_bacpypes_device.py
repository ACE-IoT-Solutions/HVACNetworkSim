import unittest
import asyncio
import json
from unittest.mock import patch, MagicMock

# Import bacpypes3 modules
from bacpypes3.vlan import VirtualNetwork
from bacpypes3.app import Application
from bacpypes3.local.device import DeviceObject
from bacpypes3.local.networkport import NetworkPortObject
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.multistate import MultiStateValueObject
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import CharacterString, Real

from src.vav_box import VAVBox

class BACpypesVAVDeviceTests(unittest.TestCase):
    """Tests for BACpypes3 implementation of VAV devices on a virtual network."""

    def setUp(self):
        """Set up the test environment with a virtual network and VAV box."""
        # Create a VAV box for testing
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
            thermal_mass=2.0
        )
        
        # We'll set up the BACpypes3 network and devices in the actual test methods
        # since they need to run in an asyncio event loop

    def test_bacpypes3_configuration_structure(self):
        """Test the structure of the BACpypes3 configuration generated for a VAV device."""
        # This doesn't need async since we're just checking the structure
        config = self.vav.create_bacpypes3_config(device_id=1001, device_name="VAV-001")
        
        # Verify top-level device configuration
        self.assertIn("object-identifier", config[0])
        self.assertEqual(config[0]["object-identifier"], "device,1001")
        self.assertEqual(config[0]["object-name"], "VAV-001")
        
        # Verify that essential points are included
        point_names = set()
        for obj in config[1:]:
            if "object-name" in obj:
                point_names.add(obj["object-name"])
        
        # Check for essential points
        essential_points = ["zone_temp", "damper_position", "reheat_valve_position", "mode"]
        for point in essential_points:
            self.assertIn(point, point_names)
    
    async def async_test_device_creation_and_properties(self):
        """Test creating a BACpypes3 device from a VAV box and verify its properties."""
        # Set up a virtual network
        vlan = VirtualNetwork("test-vlan")
        
        # Create a BACpypes device from the VAV box
        device_app = await self.vav.create_bacpypes3_device(
            device_id=1001, 
            device_name="VAV-001",
            network_interface_name="test-vlan", 
            mac_address="0x01"
        )
        
        # Verify the device was created successfully
        self.assertIsInstance(device_app, Application)
        
        # Verify device properties
        device_obj = device_app.device_object
        self.assertEqual(device_obj.objectIdentifier[1], 1001)
        self.assertEqual(device_obj.objectName, "VAV-001")
        
        # Verify object list includes our points
        object_list = device_app.objectIdentifier.values()
        essential_points = ["zone_temp", "damper_position", "reheat_valve_position", "mode"]
        
        # Check if these points exist in the object list
        for point_name in essential_points:
            found = False
            for obj in object_list:
                if hasattr(obj, "objectName") and obj.objectName == point_name:
                    found = True
                    break
            self.assertTrue(found, f"Point {point_name} not found in device objects")
    
    async def async_test_device_value_updates(self):
        """Test that the device's BACnet points get updated when the VAV box state changes."""
        # Set up a virtual network
        vlan = VirtualNetwork("test-vlan")
        
        # Create a BACpypes device from the VAV box
        device_app = await self.vav.create_bacpypes3_device(
            device_id=1001, 
            device_name="VAV-001",
            network_interface_name="test-vlan", 
            mac_address="0x01"
        )
        
        # Set initial state of the VAV
        initial_temp = self.vav.zone_temp
        
        # Record initial values of BACnet points
        zone_temp_point = None
        for obj in device_app.objectIdentifier.values():
            if hasattr(obj, "objectName") and obj.objectName == "zone_temp":
                zone_temp_point = obj
                break
        
        initial_bacnet_temp = zone_temp_point.presentValue
        
        # Change VAV state
        new_temp = initial_temp + 5
        self.vav.zone_temp = new_temp
        
        # Update the BACnet device
        await self.vav.update_bacpypes3_device(device_app)
        
        # Verify that the BACnet point was updated
        self.assertEqual(zone_temp_point.presentValue, new_temp)
    
    async def async_test_two_devices_on_network(self):
        """Test that two devices can be added to the same virtual network and discovered."""
        # Set up a virtual network
        vlan = VirtualNetwork("test-vlan")
        
        # Create a second VAV box
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
            thermal_mass=1.5
        )
        
        # Create two BACpypes devices on the same virtual network
        device1_app = await self.vav.create_bacpypes3_device(
            device_id=1001, 
            device_name="VAV-001",
            network_interface_name="test-vlan", 
            mac_address="0x01"
        )
        
        device2_app = await vav2.create_bacpypes3_device(
            device_id=1002, 
            device_name="VAV-002",
            network_interface_name="test-vlan", 
            mac_address="0x02"
        )
        
        # Create a "controller" device to discover the other devices
        controller_config = [
            {
                "object-identifier": "device,1000",
                "object-name": "Controller",
                "object-type": "device",
                "vendor-identifier": 999,
                "vendor-name": "Test",
                "model-name": "TestController",
                "protocol-version": 1,
                "protocol-revision": 19
            },
            {
                "mac-address": "0x03",
                "network-interface-name": "test-vlan",
                "network-type": "virtual",
                "object-identifier": "network-port,1",
                "object-name": "NetworkPort",
                "object-type": "network-port"
            }
        ]
        
        controller_app = await Application.from_json(controller_config)
        
        # Discover devices on the network
        i_ams = await controller_app.who_is()
        
        # Verify that both VAV devices were discovered
        device_ids = sorted([i_am.iAmDeviceIdentifier[1] for i_am in i_ams])
        self.assertEqual(device_ids, [1001, 1002])

        # Clean up
        await device1_app.close()
        await device2_app.close()
        await controller_app.close()
    
    async def async_test_read_property(self):
        """Test that we can read properties from a BACpypes device."""
        # Set up a virtual network
        vlan = VirtualNetwork("test-vlan")
        
        # Create a BACpypes device from the VAV box
        device_app = await self.vav.create_bacpypes3_device(
            device_id=1001, 
            device_name="VAV-001",
            network_interface_name="test-vlan", 
            mac_address="0x01"
        )
        
        # Create a client device to read from the VAV device
        client_config = [
            {
                "object-identifier": "device,2000",
                "object-name": "Client",
                "object-type": "device",
                "vendor-identifier": 999,
                "vendor-name": "Test",
                "model-name": "TestClient",
                "protocol-version": 1,
                "protocol-revision": 19
            },
            {
                "mac-address": "0x04",
                "network-interface-name": "test-vlan",
                "network-type": "virtual",
                "object-identifier": "network-port,1",
                "object-name": "NetworkPort",
                "object-type": "network-port"
            }
        ]
        
        client_app = await Application.from_json(client_config)
        
        # Find the VAV device on the network
        i_ams = await client_app.who_is()
        vav_address = None
        for i_am in i_ams:
            if i_am.iAmDeviceIdentifier[1] == 1001:
                vav_address = i_am.pduSource
                break
        
        self.assertIsNotNone(vav_address, "VAV device not found on network")
        
        # Read the zone temperature
        zone_temp_point = None
        for obj in device_app.objectIdentifier.values():
            if hasattr(obj, "objectName") and obj.objectName == "zone_temp":
                zone_temp_point = obj
                break
        
        # Find the object identifier for zone_temp
        zone_temp_id = zone_temp_point.objectIdentifier
        
        # Read the property
        result = await client_app.read_property(
            address=vav_address,
            objectIdentifier=zone_temp_id,
            propertyIdentifier="present-value"
        )
        
        # Verify the result
        self.assertEqual(result, self.vav.zone_temp)
        
        # Clean up
        await device_app.close()
        await client_app.close()

    async def async_test_write_property(self):
        """Test that we can write properties to a BACpypes device."""
        # Set up a virtual network
        vlan = VirtualNetwork("test-vlan")
        
        # Create a BACpypes device from the VAV box
        device_app = await self.vav.create_bacpypes3_device(
            device_id=1001, 
            device_name="VAV-001",
            network_interface_name="test-vlan", 
            mac_address="0x01"
        )
        
        # Create a client device to write to the VAV device
        client_config = [
            {
                "object-identifier": "device,2000",
                "object-name": "Client",
                "object-type": "device",
                "vendor-identifier": 999,
                "vendor-name": "Test",
                "model-name": "TestClient",
                "protocol-version": 1,
                "protocol-revision": 19
            },
            {
                "mac-address": "0x04",
                "network-interface-name": "test-vlan",
                "network-type": "virtual",
                "object-identifier": "network-port,1",
                "object-name": "NetworkPort",
                "object-type": "network-port"
            }
        ]
        
        client_app = await Application.from_json(client_config)
        
        # Find the VAV device on the network
        i_ams = await client_app.who_is()
        vav_address = None
        for i_am in i_ams:
            if i_am.iAmDeviceIdentifier[1] == 1001:
                vav_address = i_am.pduSource
                break
        
        self.assertIsNotNone(vav_address, "VAV device not found on network")
        
        # Find the setpoint object
        setpoint_point = None
        for obj in device_app.objectIdentifier.values()
            if hasattr(obj, "objectName") and obj.objectName == "zone_temp_setpoint":
                setpoint_point = obj
                break
        
        # Find the object identifier for setpoint
        setpoint_id = setpoint_point.objectIdentifier
        
        # New setpoint value
        new_setpoint = 75.0
        
        # Write the property
        await client_app.write_property(
            address=vav_address,
            objectIdentifier=setpoint_id,
            propertyIdentifier="present-value",
            propertyValue=new_setpoint,
        )
        
        # Verify the result in the device
        self.assertEqual(setpoint_point.presentValue, new_setpoint)
        
        # Clean up
        await device_app.close()
        await client_app.close()

    def test_async_device_creation_and_properties(self):
        """Run the async test for device creation and properties."""
        asyncio.run(self.async_test_device_creation_and_properties())
    
    def test_async_device_value_updates(self):
        """Run the async test for device value updates."""
        asyncio.run(self.async_test_device_value_updates())
    
    def test_async_two_devices_on_network(self):
        """Run the async test for two devices on a network."""
        asyncio.run(self.async_test_two_devices_on_network())
    
    def test_async_read_property(self):
        """Run the async test for reading properties."""
        asyncio.run(self.async_test_read_property())
    
    def test_async_write_property(self):
        """Run the async test for writing properties."""
        asyncio.run(self.async_test_write_property())

if __name__ == "__main__":
    unittest.main()