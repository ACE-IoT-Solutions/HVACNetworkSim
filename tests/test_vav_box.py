import unittest
import pytest
import math
from datetime import datetime, timedelta
import sys
import os
from unittest import mock
from src.vav_box import VAVBox

# Add the tests directory to the sys.path to import the mock_bac0 module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class TestVAVBox(unittest.TestCase):
    def setUp(self):
        # Default parameters for a typical VAV box
        self.vav = VAVBox(
            name="Zone1",
            min_airflow=100,  # CFM
            max_airflow=1000,  # CFM
            zone_temp_setpoint=72,  # °F
            deadband=2,  # °F
            discharge_air_temp_setpoint=55,  # °F
            has_reheat=True,
            zone_area=400,  # sq ft
            zone_volume=3200,  # cubic ft (8ft ceiling)
            window_area=80,  # sq ft
            window_orientation="east",  # east-facing windows
            thermal_mass=2.0  # Medium thermal mass
        )
    
    def test_initialization(self):
        """Test that the VAV box initializes with correct default values."""
        self.assertEqual(self.vav.name, "Zone1")
        self.assertEqual(self.vav.min_airflow, 100)
        self.assertEqual(self.vav.max_airflow, 1000)
        self.assertEqual(self.vav.zone_temp_setpoint, 72)
        self.assertEqual(self.vav.deadband, 2)
        self.assertEqual(self.vav.discharge_air_temp_setpoint, 55)
        self.assertTrue(self.vav.has_reheat)
        self.assertEqual(self.vav.current_airflow, self.vav.min_airflow)
        self.assertEqual(self.vav.damper_position, 0)
        self.assertEqual(self.vav.reheat_valve_position, 0)
        self.assertEqual(self.vav.mode, "deadband")

    def test_cooling_mode_transition(self):
        """Test VAV box transitions to cooling mode when zone temp rises above setpoint + deadband/2."""
        # Set up cooling condition
        self.vav.update(zone_temp=74, supply_air_temp=55)
        
        self.assertEqual(self.vav.mode, "cooling")
        self.assertGreater(self.vav.damper_position, 0)
        self.assertEqual(self.vav.reheat_valve_position, 0)
    
    def test_heating_mode_transition(self):
        """Test VAV box transitions to heating mode when zone temp falls below setpoint - deadband/2."""
        # Set up heating condition
        self.vav.update(zone_temp=67, supply_air_temp=55)
        
        self.assertEqual(self.vav.mode, "heating")
        self.assertEqual(self.vav.damper_position, self.vav.min_airflow / self.vav.max_airflow)
        self.assertGreater(self.vav.reheat_valve_position, 0)
    
    def test_deadband_operation(self):
        """Test VAV box operates in deadband mode when zone temp is within deadband range."""
        # Set up deadband condition
        self.vav.update(zone_temp=72, supply_air_temp=55)
        
        self.assertEqual(self.vav.mode, "deadband")
        self.assertEqual(self.vav.damper_position, self.vav.min_airflow / self.vav.max_airflow)
        self.assertEqual(self.vav.reheat_valve_position, 0)
    
    def test_cooling_airflow_modulation(self):
        """Test that airflow modulates based on cooling demand."""
        # Test minimum cooling
        self.vav.update(zone_temp=73, supply_air_temp=55)
        initial_airflow = self.vav.current_airflow
        
        # Test increased cooling
        self.vav.update(zone_temp=76, supply_air_temp=55)
        self.assertGreater(self.vav.current_airflow, initial_airflow)
        
        # Test maximum cooling
        self.vav.update(zone_temp=80, supply_air_temp=55)
        self.assertAlmostEqual(self.vav.current_airflow, self.vav.max_airflow)
    
    def test_reheat_operation(self):
        """Test reheat valve modulation in heating mode."""
        # Test minimum reheat
        self.vav.update(zone_temp=71, supply_air_temp=55)
        initial_reheat = self.vav.reheat_valve_position
        
        # Test increased reheat
        self.vav.update(zone_temp=68, supply_air_temp=55)
        self.assertGreater(self.vav.reheat_valve_position, initial_reheat)
        
        # Test maximum reheat
        self.vav.update(zone_temp=65, supply_air_temp=55)
        self.assertAlmostEqual(self.vav.reheat_valve_position, 1.0)
    
    def test_airflow_limits(self):
        """Test that airflow stays within configured min/max limits."""
        # Test min limit in heating mode
        self.vav.update(zone_temp=65, supply_air_temp=55)
        self.assertGreaterEqual(self.vav.current_airflow, self.vav.min_airflow)
        
        # Test max limit in cooling mode
        self.vav.update(zone_temp=85, supply_air_temp=55)
        self.assertLessEqual(self.vav.current_airflow, self.vav.max_airflow)
    
    def test_discharge_air_temp_control(self):
        """Test discharge air temperature control via reheat."""
        # Setup heating mode
        self.vav.update(zone_temp=68, supply_air_temp=55)
        
        # Check that discharge air temp is calculated based on reheat
        self.assertGreater(self.vav.get_discharge_air_temp(), 55)
    
    def test_no_reheat_configuration(self):
        """Test VAV box behavior when configured without reheat."""
        vav_no_reheat = VAVBox(
            name="Zone2",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=False
        )
        
        # Test behavior in heating demand
        vav_no_reheat.update(zone_temp=68, supply_air_temp=55)
        self.assertEqual(vav_no_reheat.reheat_valve_position, 0)
        self.assertEqual(vav_no_reheat.get_discharge_air_temp(), 55)
    
    def test_pid_control_response(self):
        """Test PID control response to varying conditions."""
        # Test cooling response over time
        self.vav.update(zone_temp=76, supply_air_temp=55)
        airflow1 = self.vav.current_airflow
        
        # Simulate zone cooling down (less aggressive response expected)
        self.vav.update(zone_temp=74, supply_air_temp=55)
        airflow2 = self.vav.current_airflow
        
        self.assertLess(airflow2, airflow1)

    def test_pid_response_heating(self):
        """Test PID control response to heating demand."""
        # Test heating response over time
        self.vav.update(zone_temp=68, supply_air_temp=55)
        reheat1 = self.vav.reheat_valve_position
        
        # Simulate zone heating up (less aggressive response expected)
        self.vav.update(zone_temp=70, supply_air_temp=55)
        reheat2 = self.vav.reheat_valve_position
        
        self.assertLess(reheat2, reheat1)
    
    def test_energy_calculation(self):
        """Test energy consumption calculation."""
        # Cooling energy
        self.vav.update(zone_temp=76, supply_air_temp=55)
        cooling_energy = self.vav.calculate_energy_usage()
        self.assertGreater(cooling_energy['cooling'], 0)
        self.assertEqual(cooling_energy['heating'], 0)
        
        # Heating energy
        self.vav.update(zone_temp=68, supply_air_temp=55)
        heating_energy = self.vav.calculate_energy_usage()
        self.assertEqual(heating_energy['cooling'], 0)
        self.assertGreater(heating_energy['heating'], 0)
    
    def test_occupancy_heat_load(self):
        """Test that adding occupants increases the heat load in the zone."""
        # First set up a stable zone at setpoint
        self.vav.update(zone_temp=72, supply_air_temp=55)
        initial_zone_temp = self.vav.zone_temp
        
        # Then add occupants and run thermal model
        self.vav.set_occupancy(5)  # 5 people
        
        # Run thermal model for 15 minutes with no VAV effect
        temp_change = self.vav.calculate_thermal_behavior(
            minutes=15,
            outdoor_temp=72,  # Neutral outdoor temp
            vav_cooling_effect=0,  # No VAV effect
            time_of_day=(8, 0)  # 8:00 AM
        )
        
        # Adding people should increase temperature
        self.assertGreater(temp_change, 0)
        
        # More people should produce more heat
        self.vav.set_occupancy(10)  # 10 people
        more_people_temp_change = self.vav.calculate_thermal_behavior(
            minutes=15,
            outdoor_temp=72,
            vav_cooling_effect=0,
            time_of_day=(8, 0)
        )
        
        # More people should cause greater temperature increase
        self.assertGreater(more_people_temp_change, temp_change)
    
    def test_solar_heat_gain(self):
        """Test that solar gain varies with time of day and window orientation."""
        # Initialize with east-facing windows
        east_vav = VAVBox(
            name="EastZone",
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
        
        # Initialize with west-facing windows
        west_vav = VAVBox(
            name="WestZone",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=80,
            window_orientation="west",
            thermal_mass=2.0
        )
        
        # Morning: East windows should get more solar gain
        east_morning_gain = east_vav.calculate_solar_gain(time_of_day=(8, 0))
        west_morning_gain = west_vav.calculate_solar_gain(time_of_day=(8, 0))
        self.assertGreater(east_morning_gain, west_morning_gain)
        
        # Afternoon: West windows should get more solar gain
        east_afternoon_gain = east_vav.calculate_solar_gain(time_of_day=(16, 0))
        west_afternoon_gain = west_vav.calculate_solar_gain(time_of_day=(16, 0))
        self.assertGreater(west_afternoon_gain, east_afternoon_gain)
        
        # Middle of the day: Both should get similar gain
        east_midday_gain = east_vav.calculate_solar_gain(time_of_day=(12, 0))
        west_midday_gain = west_vav.calculate_solar_gain(time_of_day=(12, 0))
        # They might not be exactly equal, but should be closer than morning/afternoon
        midday_diff = abs(east_midday_gain - west_midday_gain)
        morning_diff = abs(east_morning_gain - west_morning_gain)
        self.assertLess(midday_diff, morning_diff)
        
        # Night: Both should get minimal gain
        east_night_gain = east_vav.calculate_solar_gain(time_of_day=(22, 0))
        west_night_gain = west_vav.calculate_solar_gain(time_of_day=(22, 0))
        self.assertLess(east_night_gain, east_morning_gain)
        self.assertLess(west_night_gain, west_afternoon_gain)
    
    def test_thermal_behavior_with_occupancy_and_solar(self):
        """Test combined effects of occupancy, solar gain, and VAV operation."""
        # Start with a neutral zone temperature
        self.vav.update(zone_temp=72, supply_air_temp=55)
        
        # Add occupants and simulate morning with east windows
        self.vav.set_occupancy(5)
        
        # Simulate 15 minutes in the morning
        morning_temp_change = self.vav.calculate_thermal_behavior(
            minutes=15,
            outdoor_temp=75,  # Warm outside
            vav_cooling_effect=0.5,  # Some cooling
            time_of_day=(8, 0)  # Morning (high solar for east windows)
        )
        
        # Simulate 15 minutes in the evening
        evening_temp_change = self.vav.calculate_thermal_behavior(
            minutes=15,
            outdoor_temp=75,  # Same outdoor temp
            vav_cooling_effect=0.5,  # Same cooling
            time_of_day=(18, 0)  # Evening (low solar for east windows)
        )
        
        # Morning should have higher temperature change due to solar gain
        self.assertGreater(morning_temp_change, evening_temp_change)
        
        # Simulate with cooling effect
        self.vav.set_occupancy(10)  # High occupancy
        
        # Insufficient cooling
        low_cooling_change = self.vav.calculate_thermal_behavior(
            minutes=15,
            outdoor_temp=85,  # Hot outside
            vav_cooling_effect=0.3,  # Low cooling
            time_of_day=(12, 0)  # Midday
        )
        
        # Strong cooling
        high_cooling_change = self.vav.calculate_thermal_behavior(
            minutes=15,
            outdoor_temp=85,  # Hot outside
            vav_cooling_effect=0.9,  # High cooling
            time_of_day=(12, 0)  # Midday
        )
        
        # Strong cooling should result in less temperature increase or even decrease
        self.assertLess(high_cooling_change, low_cooling_change)

    def test_simulate_zone_thermal_behavior(self):
        """Test the complete simulation of zone temperature over time."""
        # Run a simulation for a full day with 15-minute intervals
        start_temp = 72
        self.vav.zone_temp = start_temp
        
        # Define test schedule
        occupied_hours = [(8, 18)]  # 8 AM to 6 PM
        occupancy = 5  # 5 people during occupied hours
        outdoor_temps = {hour: 65 + 15 * math.sin(math.pi * (hour - 5) / 12) for hour in range(24)}
        
        # Run simulation for 24 hours with 15-minute intervals
        results = self.vav.simulate_thermal_behavior(
            hours=24, 
            interval_minutes=15,
            start_hour=0,
            outdoor_temps=outdoor_temps,
            occupied_hours=occupied_hours,
            occupancy=occupancy,
            supply_air_temp=55
        )
        
        # Verify results contain the expected data
        self.assertEqual(len(results['times']), 24 * 60 // 15)  # 96 points for 15-min intervals
        self.assertEqual(len(results['zone_temps']), len(results['times']))
        self.assertEqual(len(results['vav_airflows']), len(results['times']))
        
        # Verify the zone responds to occupancy
        # Find temperatures during occupied vs unoccupied periods
        occupied_temps = []
        unoccupied_temps = []
        
        for i, time_tuple in enumerate(results['times']):
            hour, minute = time_tuple
            if any(start <= hour < end for start, end in occupied_hours):
                occupied_temps.append(results['zone_temps'][i])
            else:
                unoccupied_temps.append(results['zone_temps'][i])
        
        # Calculate average temps for comparison
        avg_occupied = sum(occupied_temps) / len(occupied_temps) if occupied_temps else 0
        avg_unoccupied = sum(unoccupied_temps) / len(unoccupied_temps) if unoccupied_temps else 0
        
        # Occupied periods should generally be warmer due to people
        self.assertGreater(avg_occupied, avg_unoccupied)
    
    def test_get_process_variables(self):
        """Test that VAV box returns a dictionary of all its process variables."""
        # Setup the VAV box with some known values
        self.vav.update(zone_temp=74, supply_air_temp=55)
        self.vav.set_occupancy(3)
        
        # Get process variables
        variables = self.vav.get_process_variables()
        
        # Check that it's a dictionary
        self.assertIsInstance(variables, dict)
        
        # Check that it contains all the important state variables
        essential_vars = [
            "name", "zone_temp", "leaving_water_temp", "current_airflow", 
            "damper_position", "reheat_valve_position", "mode", "occupancy"
        ]
        
        for var in essential_vars:
            self.assertIn(var, variables)
            
        # Check that values match the actual object properties
        self.assertEqual(variables["name"], self.vav.name)
        self.assertEqual(variables["zone_temp"], self.vav.zone_temp)
        self.assertEqual(variables["current_airflow"], self.vav.current_airflow)
        self.assertEqual(variables["damper_position"], self.vav.damper_position)
        self.assertEqual(variables["reheat_valve_position"], self.vav.reheat_valve_position)
        self.assertEqual(variables["mode"], self.vav.mode)
        self.assertEqual(variables["occupancy"], self.vav.occupancy)
    
    def test_get_process_variables_metadata(self):
        """Test that VAV box provides metadata for all process variables."""
        # Get metadata
        metadata = VAVBox.get_process_variables_metadata()
        
        # Check that it's a dictionary
        self.assertIsInstance(metadata, dict)
        
        # Check that it contains metadata for important state variables
        essential_vars = [
            "name", "zone_temp", "current_airflow", "damper_position", 
            "reheat_valve_position", "mode", "occupancy"
        ]
        
        for var in essential_vars:
            self.assertIn(var, metadata)
            
        # Check that each variable has the required metadata fields
        for var_name, var_metadata in metadata.items():
            self.assertIn("type", var_metadata)
            self.assertIn("label", var_metadata)
            self.assertIn("description", var_metadata)
            
        # Check specific metadata entries for correctness
        self.assertEqual(metadata["zone_temp"]["type"], float)
        self.assertEqual(metadata["zone_temp"]["label"], "Zone Temperature")
        self.assertEqual(metadata["zone_temp"]["unit"], "°F")
        
        self.assertEqual(metadata["occupancy"]["type"], int)
        self.assertEqual(metadata["mode"]["type"], str)
        self.assertEqual(metadata["has_reheat"]["type"], bool)
        
        # Check that options are provided for enumerated types
        self.assertIn("options", metadata["mode"])
        self.assertIn("cooling", metadata["mode"]["options"])
        self.assertIn("heating", metadata["mode"]["options"])
        self.assertIn("deadband", metadata["mode"]["options"])

    def test_create_bacnet_device(self):
        """Test creation of a BAC0 device from VAV box."""
        # Import our mock BAC0 implementation
        from mock_bac0 import BAC0, BACnetVirtualDevice, BACnetPoint
        
        # Use mock to patch the import inside the method
        with mock.patch.dict('sys.modules', {'BAC0': BAC0}):
            # Set up the VAV box with some known values
            self.vav.update(zone_temp=74, supply_air_temp=55)
            self.vav.set_occupancy(3)
        
            # Create the BACnet device
            device = self.vav.create_bacnet_device(device_id=1001, device_name="Test-VAV")
            
            # Check device properties
            self.assertEqual(device.device_id, 1001)
            self.assertEqual(device.device_name, "Test-VAV")
            
            # Check that points were created
            self.assertGreater(len(device.points), 0)
            
            # Check a few specific points
            essential_points = ["zone_temp", "damper_position", "reheat_valve_position", "mode"]
            for point_name in essential_points:
                self.assertIn(point_name, device.points)
                
            # Verify point types and units for specific points
            self.assertEqual(device.points["zone_temp"].objectType, "analogValue")
            self.assertEqual(device.points["zone_temp"].units, "°F")
            self.assertEqual(device.points["damper_position"].objectType, "analogValue")
            self.assertEqual(device.points["mode"].objectType, "multiStateValue")
            
            # Verify initial values were set
            self.assertEqual(device.points["zone_temp"].value, 74)
            self.assertEqual(device.points["occupancy"].value, 3)
            
            # Test mode enumeration conversion (should be 1-based index in BACnet MSV)
            metadata = VAVBox.get_process_variables_metadata()
            mode_options = metadata["mode"]["options"]
            expected_mode_index = mode_options.index(self.vav.mode) + 1
            self.assertEqual(device.points["mode"].value, expected_mode_index)
            
            # Test that update_from_vav method updates values
            self.vav.update(zone_temp=76, supply_air_temp=55)  # Change some values
            device.update_from_vav()  # Update the device
            
            # Verify values were updated
            self.assertEqual(device.points["zone_temp"].value, 76)
            
            # Test with default device_id and name
            device2 = self.vav.create_bacnet_device()
            self.assertIsNotNone(device2.device_id)
            self.assertEqual(device2.device_name, f"VAV-{self.vav.name}")

if __name__ == '__main__':
    unittest.main()