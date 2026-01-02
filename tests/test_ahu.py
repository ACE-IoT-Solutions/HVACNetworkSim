import unittest
from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit

class TestAirHandlingUnit(unittest.TestCase):
    def setUp(self):
        # Create sample VAV boxes
        self.vav1 = VAVBox(
            name="Zone1",
            min_airflow=100,  # CFM
            max_airflow=1000,  # CFM
            zone_temp_setpoint=72,  # °F
            deadband=2,  # °F
            discharge_air_temp_setpoint=55,  # °F
            has_reheat=True
        )
        
        self.vav2 = VAVBox(
            name="Zone2",
            min_airflow=150,  # CFM
            max_airflow=1200,  # CFM
            zone_temp_setpoint=70,  # °F
            deadband=2,  # °F
            discharge_air_temp_setpoint=55,  # °F
            has_reheat=True
        )
        
        self.vav3 = VAVBox(
            name="Zone3",
            min_airflow=200,  # CFM
            max_airflow=1500,  # CFM
            zone_temp_setpoint=74,  # °F
            deadband=2,  # °F
            discharge_air_temp_setpoint=55,  # °F
            has_reheat=False  # This zone doesn't have reheat
        )
        
        # Create AHU with these VAV boxes (default is chilled water)
        self.ahu = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",  # Using chilled water for cooling
            supply_air_temp_setpoint=55,  # °F
            min_supply_air_temp=52,  # °F
            max_supply_air_temp=65,  # °F
            max_supply_airflow=5000,  # CFM
            vav_boxes=[self.vav1, self.vav2, self.vav3]
        )
        
        # Create a DX AHU for comparison
        self.dx_ahu = AirHandlingUnit(
            name="AHU-2",
            cooling_type="dx",  # Using direct expansion cooling
            supply_air_temp_setpoint=55,  # °F
            min_supply_air_temp=52,  # °F
            max_supply_air_temp=65,  # °F
            max_supply_airflow=5000,  # CFM
            vav_boxes=[self.vav1, self.vav2, self.vav3]
        )
    
    def test_initialization(self):
        """Test AHU initializes with correct default values."""
        self.assertEqual(self.ahu.name, "AHU-1")
        self.assertEqual(self.ahu.cooling_type, "chilled_water")
        self.assertEqual(self.ahu.supply_air_temp_setpoint, 55)
        self.assertEqual(self.ahu.min_supply_air_temp, 52)
        self.assertEqual(self.ahu.max_supply_air_temp, 65)
        self.assertEqual(self.ahu.max_supply_airflow, 5000)
        self.assertEqual(len(self.ahu.vav_boxes), 3)
        self.assertEqual(self.ahu.current_supply_air_temp, 55)
        self.assertEqual(self.ahu.current_total_airflow, 0)
        self.assertEqual(self.ahu.cooling_valve_position, 0)
        self.assertEqual(self.ahu.heating_valve_position, 0)
        
        # Check DX AHU initialization
        self.assertEqual(self.dx_ahu.name, "AHU-2")
        self.assertEqual(self.dx_ahu.cooling_type, "dx")
        self.assertEqual(self.dx_ahu.compressor_stages, 2)  # Default value
    
    def test_add_vav_box(self):
        """Test adding a VAV box to the AHU."""
        vav4 = VAVBox(
            name="Zone4",
            min_airflow=120,
            max_airflow=800,
            zone_temp_setpoint=73,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True
        )
        
        self.ahu.add_vav_box(vav4)
        
        self.assertEqual(len(self.ahu.vav_boxes), 4)
        self.assertIn(vav4, self.ahu.vav_boxes)
    
    def test_update_with_zone_temps(self):
        """Test updating AHU and VAV boxes with zone temperatures."""
        # Set zone temperatures for the update
        zone_temps = {
            "Zone1": 75,  # Cooling needed (ensuring it's above setpoint + deadband/2)
            "Zone2": 68,  # Heating needed
            "Zone3": 77   # Cooling needed (ensuring it's above setpoint + deadband/2)
        }
        
        # Update with these zone temperatures
        self.ahu.update(zone_temps, outdoor_temp=80)
        
        # Check VAV boxes were updated properly
        self.assertEqual(self.vav1.zone_temp, 75)
        self.assertEqual(self.vav2.zone_temp, 68)
        self.assertEqual(self.vav3.zone_temp, 77)
        
        # Check VAV modes were set correctly
        self.assertEqual(self.vav1.mode, "cooling")
        self.assertEqual(self.vav2.mode, "heating")
        self.assertEqual(self.vav3.mode, "cooling")
    
    def test_total_airflow_calculation(self):
        """Test that the AHU correctly calculates total airflow from VAV boxes."""
        # Set zone temperatures to get different airflows
        zone_temps = {
            "Zone1": 76,  # High cooling demand
            "Zone2": 72,  # In deadband
            "Zone3": 77   # High cooling demand
        }
        
        # Update with these zone temperatures
        self.ahu.update(zone_temps, outdoor_temp=85)
        
        # Get individual airflows for verification
        vav1_airflow = self.vav1.current_airflow
        vav2_airflow = self.vav2.current_airflow
        vav3_airflow = self.vav3.current_airflow
        
        # Check total airflow is sum of individual VAV airflows
        expected_total = vav1_airflow + vav2_airflow + vav3_airflow
        self.assertAlmostEqual(self.ahu.current_total_airflow, expected_total)
    
    def test_supply_air_temp_control(self):
        """Test AHU supply air temperature control based on outdoor temperature."""
        # First update with hot outdoor temp
        self.ahu.update({"Zone1": 72, "Zone2": 72, "Zone3": 72}, outdoor_temp=90)
        hot_outdoor_supply_temp = self.ahu.current_supply_air_temp
        
        # Then update with cold outdoor temp
        self.ahu.update({"Zone1": 72, "Zone2": 72, "Zone3": 72}, outdoor_temp=30)
        cold_outdoor_supply_temp = self.ahu.current_supply_air_temp
        
        # Should maintain setpoint regardless of outdoor temperature
        self.assertAlmostEqual(hot_outdoor_supply_temp, self.ahu.supply_air_temp_setpoint)
        self.assertAlmostEqual(cold_outdoor_supply_temp, self.ahu.supply_air_temp_setpoint)
    
    def test_cooling_valve_modulation(self):
        """Test cooling valve modulation based on cooling demand."""
        # High cooling demand
        self.ahu.update({"Zone1": 76, "Zone2": 75, "Zone3": 78}, outdoor_temp=80)
        high_cooling_valve = self.ahu.cooling_valve_position
        
        # Medium cooling demand
        self.ahu.update({"Zone1": 73, "Zone2": 72, "Zone3": 75}, outdoor_temp=70)
        medium_cooling_valve = self.ahu.cooling_valve_position
        
        # Low/no cooling demand
        self.ahu.update({"Zone1": 71, "Zone2": 70, "Zone3": 72}, outdoor_temp=60)
        low_cooling_valve = self.ahu.cooling_valve_position
        
        # Check relative valve positions
        self.assertGreater(high_cooling_valve, medium_cooling_valve)
        self.assertGreater(medium_cooling_valve, low_cooling_valve)
    
    def test_heating_valve_modulation(self):
        """Test heating valve modulation based on heating demand."""
        # High heating demand
        self.ahu.update({"Zone1": 68, "Zone2": 66, "Zone3": 69}, outdoor_temp=30)
        high_heating_valve = self.ahu.heating_valve_position
        
        # Medium heating demand
        self.ahu.update({"Zone1": 71, "Zone2": 69, "Zone3": 72}, outdoor_temp=40)
        medium_heating_valve = self.ahu.heating_valve_position
        
        # Low/no heating demand
        self.ahu.update({"Zone1": 73, "Zone2": 71, "Zone3": 75}, outdoor_temp=50)
        low_heating_valve = self.ahu.heating_valve_position
        
        # Check relative valve positions
        self.assertGreater(high_heating_valve, medium_heating_valve)
        self.assertGreater(medium_heating_valve, low_heating_valve)
    
    def test_supply_temp_reset(self):
        """Test supply air temperature reset based on zone demands."""
        # Create an AHU with reset enabled
        ahu_with_reset = AirHandlingUnit(
            name="AHU-2",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=5000,
            vav_boxes=[self.vav1, self.vav2, self.vav3],
            enable_supply_temp_reset=True
        )
        
        # Test reset for mostly cooling
        ahu_with_reset.update({"Zone1": 75, "Zone2": 73, "Zone3": 77}, outdoor_temp=85)
        cooling_supply_temp = ahu_with_reset.current_supply_air_temp
        
        # Test reset for mostly heating
        ahu_with_reset.update({"Zone1": 69, "Zone2": 67, "Zone3": 71}, outdoor_temp=40)
        heating_supply_temp = ahu_with_reset.current_supply_air_temp
        
        # Supply temp should be lower for cooling, higher for heating
        self.assertLess(cooling_supply_temp, heating_supply_temp)
        
        # Should be within limits
        self.assertGreaterEqual(cooling_supply_temp, ahu_with_reset.min_supply_air_temp)
        self.assertLessEqual(heating_supply_temp, ahu_with_reset.max_supply_air_temp)
    
    def test_energy_calculation(self):
        """Test calculation of energy usage by the AHU."""
        # Set up a scenario with both heating and cooling
        self.ahu.update({"Zone1": 74, "Zone2": 68, "Zone3": 72}, outdoor_temp=45)
        
        # Get energy usage
        energy = self.ahu.calculate_energy_usage()
        
        # Basic checks
        self.assertIn("cooling", energy)
        self.assertIn("heating", energy)
        self.assertIn("fan", energy)
        self.assertIn("total", energy)
        
        # Total should be sum of components
        expected_total = energy["cooling"] + energy["heating"] + energy["fan"]
        self.assertAlmostEqual(energy["total"], expected_total)
    
    def test_fan_power_calculation(self):
        """Test calculation of fan power based on airflow."""
        # First test with low airflow
        self.ahu.update({"Zone1": 72, "Zone2": 71, "Zone3": 73}, outdoor_temp=70)
        low_airflow = self.ahu.current_total_airflow
        low_fan_power = self.ahu.calculate_fan_power()
        
        # Then test with high airflow
        self.ahu.update({"Zone1": 77, "Zone2": 76, "Zone3": 78}, outdoor_temp=90)
        high_airflow = self.ahu.current_total_airflow
        high_fan_power = self.ahu.calculate_fan_power()
        
        # Fan power should increase with airflow
        self.assertGreater(high_airflow, low_airflow)
        self.assertGreater(high_fan_power, low_fan_power)
    
    def test_chilled_water_flow_calculation(self):
        """Test calculation of chilled water flow based on cooling load."""
        # Test low cooling load
        self.ahu.update({"Zone1": 73, "Zone2": 72, "Zone3": 73}, outdoor_temp=75)
        low_cooling_load = self.ahu.cooling_energy
        low_chw_flow = self.ahu.calculate_chilled_water_flow()
        
        # Test high cooling load
        self.ahu.update({"Zone1": 78, "Zone2": 77, "Zone3": 78}, outdoor_temp=95)
        high_cooling_load = self.ahu.cooling_energy
        high_chw_flow = self.ahu.calculate_chilled_water_flow()
        
        # Chilled water flow should increase with cooling load
        self.assertGreater(high_cooling_load, low_cooling_load)
        self.assertGreater(high_chw_flow, low_chw_flow)
        
        # Check units (GPM)
        self.assertGreaterEqual(low_chw_flow, 0)
        self.assertLess(high_chw_flow, 1000)  # Reasonable upper bound for a medium AHU
    
    def test_dx_compressor_staging(self):
        """Test DX compressor staging based on cooling load."""
        # Test with low cooling demand (should use fewer stages)
        self.dx_ahu.update({"Zone1": 73, "Zone2": 72, "Zone3": 73}, outdoor_temp=75)
        low_cooling_load = self.dx_ahu.cooling_energy
        low_active_stages = self.dx_ahu.active_compressor_stages
        
        # Test with high cooling demand (should use more stages)
        self.dx_ahu.update({"Zone1": 78, "Zone2": 77, "Zone3": 78}, outdoor_temp=95)
        high_cooling_load = self.dx_ahu.cooling_energy
        high_active_stages = self.dx_ahu.active_compressor_stages
        
        # Higher cooling load should activate more compressor stages
        self.assertGreater(high_cooling_load, low_cooling_load)
        self.assertGreaterEqual(high_active_stages, low_active_stages)
        
        # Verify within bounds
        self.assertGreaterEqual(low_active_stages, 0)
        self.assertLessEqual(high_active_stages, self.dx_ahu.compressor_stages)
    
    def test_cooling_energy_source_specific_calculation(self):
        """Test that energy calculations are specific to the cooling type."""
        # Set up identical conditions for both AHUs
        zone_temps = {"Zone1": 76, "Zone2": 75, "Zone3": 76}
        outdoor_temp = 90
        
        # Update both AHUs
        self.ahu.update(zone_temps, outdoor_temp)
        self.dx_ahu.update(zone_temps, outdoor_temp)
        
        # Get energy usage
        chw_energy = self.ahu.calculate_energy_usage()
        dx_energy = self.dx_ahu.calculate_energy_usage()
        
        # Both should calculate cooling energy
        self.assertGreater(chw_energy["cooling"], 0)
        self.assertGreater(dx_energy["cooling"], 0)
        
        # Chilled water AHU should have water flow
        self.assertGreater(self.ahu.calculate_chilled_water_flow(), 0)
        
        # DX AHU should have active compressor stages
        self.assertGreater(self.dx_ahu.active_compressor_stages, 0)
        
        # Energy calculations should be different due to different efficiency models
        self.assertNotEqual(chw_energy["cooling"], dx_energy["cooling"])
    
    def test_chilled_water_valve_control(self):
        """Test that chilled water valve position responds to cooling load."""
        # Low cooling load
        self.ahu.update({"Zone1": 73, "Zone2": 72, "Zone3": 73}, outdoor_temp=75)
        low_valve_pos = self.ahu.cooling_valve_position
        
        # Medium cooling load
        self.ahu.update({"Zone1": 75, "Zone2": 74, "Zone3": 75}, outdoor_temp=85)
        med_valve_pos = self.ahu.cooling_valve_position
        
        # High cooling load
        self.ahu.update({"Zone1": 78, "Zone2": 77, "Zone3": 78}, outdoor_temp=95)
        high_valve_pos = self.ahu.cooling_valve_position
        
        # Valve position should increase with cooling load
        self.assertLessEqual(low_valve_pos, med_valve_pos)
        self.assertLessEqual(med_valve_pos, high_valve_pos)
        
        # Verify bounds
        self.assertGreaterEqual(low_valve_pos, 0)
        self.assertLessEqual(high_valve_pos, 1)
        
    def test_get_process_variables(self):
        """Test that AHU returns a dictionary of all process variables."""
        # Set up with some known values
        self.ahu.update({"Zone1": 75, "Zone2": 73, "Zone3": 77}, outdoor_temp=85)
        
        # Get process variables
        variables = self.ahu.get_process_variables()
        
        # Check that it's a dictionary
        self.assertIsInstance(variables, dict)
        
        # Check that it contains essential state variables
        essential_vars = [
            "name", "cooling_type", "current_supply_air_temp", "current_total_airflow",
            "cooling_valve_position", "heating_valve_position", "fan_power",
            "cooling_energy", "heating_energy", "fan_energy", "total_energy"
        ]
        
        for var in essential_vars:
            self.assertIn(var, variables)
            
        # Check that values match the actual object properties
        self.assertEqual(variables["name"], self.ahu.name)
        self.assertEqual(variables["cooling_type"], self.ahu.cooling_type)
        self.assertEqual(variables["current_supply_air_temp"], self.ahu.current_supply_air_temp)
        self.assertEqual(variables["current_total_airflow"], self.ahu.current_total_airflow)
        self.assertEqual(variables["cooling_valve_position"], self.ahu.cooling_valve_position)
        self.assertEqual(variables["heating_valve_position"], self.ahu.heating_valve_position)
        
        # Check that it includes information about connected VAV boxes
        self.assertEqual(variables["num_vav_boxes"], len(self.ahu.vav_boxes))
        self.assertEqual(len(variables["vav_box_names"]), len(self.ahu.vav_boxes))
        
        # Check that DX AHU includes specific variables
        dx_variables = self.dx_ahu.get_process_variables()
        self.assertIn("active_compressor_stages", dx_variables)
        self.assertIn("compressor_stages", dx_variables)
        
        # Check that CHW AHU includes specific variables
        chw_variables = self.ahu.get_process_variables()
        self.assertIn("chilled_water_flow", chw_variables)
        self.assertIn("chilled_water_delta_t", chw_variables)
    
    def test_get_process_variables_metadata(self):
        """Test that AHU provides metadata for all process variables."""
        # Get metadata
        metadata = AirHandlingUnit.get_process_variables_metadata()
        
        # Check that it's a dictionary
        self.assertIsInstance(metadata, dict)
        
        # Check that it contains metadata for essential state variables
        essential_vars = [
            "name", "cooling_type", "current_supply_air_temp", "current_total_airflow",
            "cooling_valve_position", "heating_valve_position", "fan_power"
        ]
        
        for var in essential_vars:
            self.assertIn(var, metadata)
            
        # Check that each variable has the required metadata fields
        for var_name, var_metadata in metadata.items():
            self.assertIn("type", var_metadata)
            self.assertIn("label", var_metadata)
            self.assertIn("description", var_metadata)
            
        # Check specific metadata entries for correctness
        self.assertEqual(metadata["current_supply_air_temp"]["type"], float)
        self.assertEqual(metadata["current_supply_air_temp"]["label"], "Current Supply Air Temperature")
        self.assertEqual(metadata["current_supply_air_temp"]["unit"], "°F")
        
        self.assertEqual(metadata["cooling_type"]["type"], str)
        self.assertEqual(metadata["num_vav_boxes"]["type"], int)
        self.assertEqual(metadata["vav_box_names"]["type"], list)
        self.assertEqual(metadata["enable_supply_temp_reset"]["type"], bool)
        
        # Check that options are provided for enumerated types
        self.assertIn("options", metadata["cooling_type"])
        self.assertIn("chilled_water", metadata["cooling_type"]["options"])
        self.assertIn("dx", metadata["cooling_type"]["options"])
        
        # Check that both cooling types' variables are included
        self.assertIn("chilled_water_flow", metadata)
        self.assertIn("active_compressor_stages", metadata)

if __name__ == '__main__':
    unittest.main()