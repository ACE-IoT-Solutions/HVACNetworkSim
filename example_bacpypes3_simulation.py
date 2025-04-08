#!/usr/bin/env python3
"""
Example of VAV Box simulation with BACnet integration using BACpypes3.
Runs an accelerated simulation at 1 hour per minute (60x speed).

This example demonstrates:
1. Creating multiple VAV boxes
2. Adding them to a BACpypes3 virtual network
3. Running a simulation with multiple devices communicating
4. Including a "controller" device that can read/write to the VAV devices
"""

import asyncio
import math
import random
import signal
import sys
from datetime import datetime

from bacpypes3.vlan import VirtualNetwork
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.multistate import MultiStateValueObject

from src.vav_box import VAVBox

# Global references to keep objects alive
all_devices = []
virtual_network = None
controller_app = None
exit_event = None
app: Application

async def create_controller(network_name, mac_address="0x01"):
    """Create a controller device that can interact with the VAV boxes."""
    # Create JSON-compatible configuration for the controller
    controller_config = [
        # Device Object
        {
            "apdu-segment-timeout": 1000,
            "apdu-timeout": 3000,
            "object-identifier": "device,1000",
            "object-name": "BACnet Controller",
            "object-type": "device",
            "vendor-identifier": 999,
            "vendor-name": "HVACNetwork",
            "model-name": "Controller",
            "protocol-version": 1,
            "protocol-revision": 22,
            "application-software-version": "1.0",
            "description": "Central BACnet Controller"
        },
        {
            "bacnet-ip-mode": "normal",
            "bacnet-ip-udp-port": 47808,
            "changes-pending": False,
            "ip-address": "10.88.0.24",
            "ip-subnet-mask": "255.255.0.0",
            "link-speed": 0.0,
            "mac-address": "10.88.0.24:47808",
            "network-number": 100,
            "network-number-quality": "configured",
            "network-type": "ipv4",
            "object-identifier": "network-port,1",
            "object-name": "NetworkPort-1",
            "object-type": "network-port",
            "out-of-service": False,
            "protocol-level": "bacnet-application",
            "reliability": "no-fault-detected"
        },
        # Network Port
        {
            "changes-pending": False,
            "mac-address": "0x02",
            "network-interface-name": "hvac-network",
            "network-number": 200,
            "network-number-quality": "configured",
            "network-type": "virtual",
            "object-identifier": "network-port,2",
            "object-name": "NetworkPort-2",
            "object-type": "network-port",
            "out-of-service": False,
            "protocol-level": "bacnet-application",
            "reliability": "no-fault-detected"
        }
    ]
    
    # Create the controller using from_json method (which is synchronous)
    controller = Application.from_json(controller_config)
    
    print(f"Created controller device (ID: 1000) on network: {network_name}")
    
    return controller

async def discover_devices(controller_app):
    """Discover devices on the network using Who-Is service."""
    print("\nDiscovering devices on the network...")
    
    # Use Who-Is to discover devices
    i_ams = await controller_app.who_is()
    
    for i_am in i_ams:
        print(f"Found device: {i_am.iAmDeviceIdentifier[1]} at {i_am.pduSource}")
    
    return i_ams

async def read_vav_properties(controller_app, device_address, object_id, property_id="present-value"):
    """Read a property from a VAV device."""
    try:
        result = await controller_app.read_property(
            address=device_address,
            objid=object_id,
            prop=property_id
        )
        return result
    except Exception as e:
        print(f"Error reading property: {e}")
        return None

async def read_vav_state(controller_app, i_am):
    """Read the state of a VAV device."""
    device_id = i_am.iAmDeviceIdentifier[1]
    device_address = i_am.pduSource
    
    # Key properties to read
    properties = [
        ("analog-value,1", "zone_temp"),
        ("analog-value,2", "damper_position"), 
        ("analog-value,3", "reheat_valve_position"),
        ("multi-state-value,4", "mode")
    ]
    
    print(f"\nReading state of device {device_id}:")
    
    state = {}
    for obj_id, name in properties:
        try:
            value = await read_vav_properties(controller_app, device_address, obj_id)
            
            # For multi-state values, try to read state-text and convert numeric value to text
            if obj_id.startswith("multi-state"):
                try:
                    state_text = await read_vav_properties(
                        controller_app, device_address, obj_id, "state-text"
                    )
                    if state_text and 1 <= value <= len(state_text):
                        value = f"{value} ({state_text[value-1]})"
                except Exception:
                    pass
                    
            state[name] = value
            print(f"  {name}: {value}")
        except:
            print(f"Error reading property: {device_address} - {obj_id} - {name}")
    
    return state

async def simulate_vav_box(vav, app, hours_per_minute=60, simulation_time=24):
    """Simulate a VAV box for a specified period, updating its BACnet device."""
    
    # Define a 24-hour period of outdoor temperatures with a sine wave pattern
    # Coldest at 5 AM, warmest at 5 PM
    outdoor_temps = {hour: 65 + 15 * math.sin(math.pi * (hour - 5) / 12) for hour in range(24)}
    
    # Office occupied from 8 AM to 6 PM
    occupied_hours = [(8, 18)]
    occupancy = 5  # 5 people during occupied hours
    
    # Simulation start time - 6 AM
    start_hour = 6
    current_hour = start_hour
    
    # Constant AHU supply air temperature
    supply_air_temp = 55  # °F
    
    # Calculate sleep time for simulation speed
    sleep_time = 60 / hours_per_minute  # seconds per simulated hour
    
    print(f"\nStarting simulation for VAV box {vav.name}...")
    print(f"Speed: {hours_per_minute}x (1 hour per {sleep_time:.1f} seconds)")
    
    # Run for specified simulation period (in hours)
    end_hour = start_hour + simulation_time
    
    try:
        while True and not exit_event.is_set():
            # Get current simulation hour (wrapped to 0-23)
            hour = current_hour % 24
            minute = 0
            
            # Get temperature for current hour
            outdoor_temp = outdoor_temps[hour]
            
            # Check if occupied based on time of day
            is_occupied = any(start <= hour < end for start, end in occupied_hours)
            occupancy_count = occupancy if is_occupied else 0
            
            # Add some random variation to make it more realistic
            outdoor_temp += random.uniform(-1, 1)  # ±1°F variation
            
            # Set occupancy
            vav.set_occupancy(occupancy_count)
            
            # Update VAV box with current conditions
            vav.update(vav.zone_temp, supply_air_temp)
            
            # Simulate thermal behavior for 1 hour
            vav_effect = 0
            if vav.mode == "cooling":
                vav_effect = vav.current_airflow / vav.max_airflow
            elif vav.mode == "heating" and vav.has_reheat:
                vav_effect = -vav.reheat_valve_position
                
            temp_change = vav.calculate_thermal_behavior(
                minutes=60,  # 1 hour
                outdoor_temp=outdoor_temp,
                vav_cooling_effect=vav_effect,
                time_of_day=(hour, minute)
            )
            
            # Update zone temperature with calculated change
            vav.zone_temp += temp_change
            
            # Update the BACnet device
            await vav.update_bacpypes3_device(app)
            
            # Display current simulation time and key values
            time_str = f"{hour:02d}:{minute:02d}"
            print(f"{vav.name} - Time: {time_str}, Outdoor: {outdoor_temp:.1f}°F, " + 
                  f"Zone: {vav.zone_temp:.1f}°F, Mode: {vav.mode}, " +
                  f"Airflow: {vav.current_airflow:.0f} CFM")
            
            # Move to next hour
            current_hour += 1
            
            # Sleep for the appropriate time to maintain simulation speed
            await asyncio.sleep(sleep_time)
            
    except asyncio.CancelledError:
        print(f"\nSimulation for {vav.name} cancelled.")
    except Exception as e:
        print(f"\nError in {vav.name} simulation: {e}")
    finally:
        print(f"Simulation for {vav.name} stopped at hour {current_hour}.")

async def controller_monitoring(controller_app, monitoring_interval=5):
    """Periodically monitor VAV devices from the controller."""
    try:
        discovered_devices = []
        
        while not exit_event.is_set():
            # Every minute, discover devices
            try:
                # Discover devices
                i_ams = await discover_devices(controller_app)
                discovered_devices = i_ams
                
                # Read state from each device
                for i_am in i_ams:
                    await read_vav_state(controller_app, i_am)
                    
            except Exception as e:
                print(f"Controller monitoring error: {e}")
                
            # Wait before next monitoring cycle
            await asyncio.sleep(monitoring_interval)
            
    except asyncio.CancelledError:
        print("\nController monitoring cancelled.")
    except Exception as e:
        print(f"\nError in controller monitoring: {e}")
    finally:
        print("Controller monitoring stopped.")

async def main():
    global all_devices, virtual_network, controller_app, exit_event
    
    # Create an exit event for clean shutdown
    exit_event = asyncio.Event()
    
    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    
    try:
        # Create a virtual network
        network_name = "hvac-network"
        print(f"Creating virtual BACnet network: {network_name}")
        virtual_network = VirtualNetwork(network_name)
        print(f"Network created successfully: {virtual_network.__class__.__name__}")
        # Create a controller device
        controller_app = await create_controller(network_name)
        all_devices.append(controller_app)  # Keep reference for cleanup
        await asyncio.sleep(1.0)
        print("\nCreated VAV boxes and controller on the BACnet network")
        
        # Create VAV boxes
        vav_configs = [
            {
                "name": "Office-1",
                "min_airflow": 100,
                "max_airflow": 1000,
                "zone_temp_setpoint": 72,
                "deadband": 2,
                "discharge_air_temp_setpoint": 55,
                "has_reheat": True,
                "zone_area": 400,
                "zone_volume": 3200,
                "window_area": 80,
                "window_orientation": "east",
                "thermal_mass": 2.0,
                "device_id": 1001,
                "mac_address": "0x0A"
            },
            {
                "name": "Office-2",
                "min_airflow": 120,
                "max_airflow": 1200,
                "zone_temp_setpoint": 73,
                "deadband": 2,
                "discharge_air_temp_setpoint": 55,
                "has_reheat": True,
                "zone_area": 450,
                "zone_volume": 3600,
                "window_area": 100,
                "window_orientation": "south",
                "thermal_mass": 1.8,
                "device_id": 1002,
                "mac_address": "0x0B"
            },
            {
                "name": "Conference",
                "min_airflow": 200,
                "max_airflow": 2000,
                "zone_temp_setpoint": 70,
                "deadband": 2,
                "discharge_air_temp_setpoint": 55,
                "has_reheat": True,
                "zone_area": 800,
                "zone_volume": 6400,
                "window_area": 150,
                "window_orientation": "west",
                "thermal_mass": 1.5,
                "device_id": 1003,
                "mac_address": "0x0C"
            }
        ]
        
        # Create VAV boxes and applications
        vav_devices = []
        for config in vav_configs:
            device_id = config.pop("device_id")
            mac_address = config.pop("mac_address") 
            
            # Create the VAV box
            vav = VAVBox(**config)
            
            # Create BACpypes device
            app = vav.create_bacpypes3_device(
                device_id=device_id,
                device_name=f"VAV-{vav.name}",
                network_interface_name=network_name,
                mac_address=mac_address
            )
            await asyncio.sleep(0.1) 
            # Store for simulation
            vav_devices.append((vav, app))
            all_devices.append(app)  # Keep reference for cleanup
        
        
        # Discover devices on the network
        # await discover_devices(controller_app)
        
        # Start simulations for each VAV box
        simulation_tasks = []
        for vav, app in vav_devices:
            simulation_tasks.append(
                asyncio.create_task(
                    simulate_vav_box(vav, app, hours_per_minute=60, simulation_time=24)
                )
            )
        
        # Start controller monitoring
        # monitoring_task = asyncio.create_task(
        #     controller_monitoring(controller_app, monitoring_interval=10)
        # )
        
        # Wait for all tasks to complete
        await asyncio.gather(*simulation_tasks,
                            #  monitoring_task
                             )
        
    except Exception as e:
        import traceback
        print(f"Error in main: {e}")
        traceback.print_exc()
    finally:
        # Clean shutdown
        await shutdown()

async def shutdown():
    """Clean shutdown of the application."""
    global exit_event, all_devices
    
    # Signal all tasks to exit
    if exit_event and not exit_event.is_set():
        print("\nShutting down...")
        exit_event.set()
    
    # Close all devices - BACpypes3 Application objects don't need explicit closing
    if all_devices:
        for app in all_devices:
            try:
                # Find the device object
                for obj in app.objectIdentifier.values():
                    if hasattr(obj, "objectIdentifier") and obj.objectIdentifier[0] == "device":
                        print(f"Cleaning up BACnet device: {obj.objectName} (ID: {obj.objectIdentifier[1]})")
                        break
                # Nothing else to do - BACpypes3 handles cleanup automatically
            except Exception as e:
                print(f"Error during device cleanup: {e}")
    
    print("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This will be handled by the signal handler in main()
        pass
    except Exception as e:
        print(f"Unhandled exception: {e}")