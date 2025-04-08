import unittest
import pytest
import math
from datetime import datetime
from src.chiller import Chiller
from src.cooling_tower import CoolingTower

class TestChiller(unittest.TestCase):
    def setUp(self):
        # Create both types of chillers for testing
        self.water_cooled_chiller = Chiller(
            name="CH-1",
            cooling_type="water_cooled",
            capacity=500,  # Nominal capacity in tons
            design_cop=6.5,  # Coefficient of Performance at design conditions
            design_entering_condenser_temp=85,  # °F for water-cooled
            design_leaving_chilled_water_temp=44,  # °F
            min_part_load_ratio=0.1,  # 10% minimum load
            design_chilled_water_flow=1200,  # Chilled water flow in GPM
            design_condenser_water_flow=1500  # Condenser water flow in GPM (for water-cooled)
        )
        
        self.air_cooled_chiller = Chiller(
            name="CH-2",
            cooling_type="air_cooled",
            capacity=300,  # Nominal capacity in tons
            design_cop=3.2,  # Lower COP for air-cooled
            design_entering_condenser_temp=95,  # °F for air-cooled (ambient dry bulb)
            design_leaving_chilled_water_temp=44,  # °F
            min_part_load_ratio=0.15,  # 15% minimum load
            design_chilled_water_flow=720  # Chilled water flow in GPM
        )
        
        # Create cooling tower for water-cooled chiller
        self.cooling_tower = CoolingTower(
            name="CT-1",
            capacity=600,  # Slightly larger than chiller (tons)
            design_approach=5,
            design_range=10,
            design_wet_bulb=76,
            min_speed=20,
            tower_type="counterflow",
            fan_power=50,
            num_cells=2
        )
    
    def test_initialization(self):
        """Test that chillers initialize with correct default values."""
        # Water-cooled chiller
        self.assertEqual(self.water_cooled_chiller.name, "CH-1")
        self.assertEqual(self.water_cooled_chiller.cooling_type, "water_cooled")
        self.assertEqual(self.water_cooled_chiller.capacity, 500)
        self.assertEqual(self.water_cooled_chiller.design_cop, 6.5)
        self.assertEqual(self.water_cooled_chiller.design_entering_condenser_temp, 85)
        self.assertEqual(self.water_cooled_chiller.design_leaving_chilled_water_temp, 44)
        self.assertEqual(self.water_cooled_chiller.min_part_load_ratio, 0.1)
        self.assertEqual(self.water_cooled_chiller.design_chilled_water_flow, 1200)
        self.assertEqual(self.water_cooled_chiller.design_condenser_water_flow, 1500)
        self.assertEqual(self.water_cooled_chiller.current_load, 0)
        self.assertEqual(self.water_cooled_chiller.entering_chilled_water_temp, 54)  # Default ECWT
        self.assertEqual(self.water_cooled_chiller.leaving_chilled_water_temp, 44)  # Default LCWT
        self.assertEqual(self.water_cooled_chiller.entering_condenser_temp, 85)  # Default ECWT
        self.assertEqual(self.water_cooled_chiller.current_cop, 0)  # Off by default
        
        # Air-cooled chiller
        self.assertEqual(self.air_cooled_chiller.name, "CH-2")
        self.assertEqual(self.air_cooled_chiller.cooling_type, "air_cooled")
        self.assertEqual(self.air_cooled_chiller.capacity, 300)
        self.assertEqual(self.air_cooled_chiller.design_cop, 3.2)
        self.assertEqual(self.air_cooled_chiller.design_entering_condenser_temp, 95)
        self.assertEqual(self.air_cooled_chiller.design_leaving_chilled_water_temp, 44)
        self.assertEqual(self.air_cooled_chiller.min_part_load_ratio, 0.15)
        self.assertEqual(self.air_cooled_chiller.design_chilled_water_flow, 720)
        self.assertIsNone(self.air_cooled_chiller.design_condenser_water_flow)  # Not applicable
        self.assertEqual(self.air_cooled_chiller.entering_condenser_temp, 95)  # Default ambient
    
    def test_connect_cooling_tower(self):
        """Test connecting a cooling tower to a water-cooled chiller."""
        # Connect cooling tower
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Verify connection
        self.assertEqual(self.water_cooled_chiller.cooling_tower, self.cooling_tower)
        
        # Verify that connecting to air-cooled raises an error
        with self.assertRaises(ValueError):
            self.air_cooled_chiller.connect_cooling_tower(self.cooling_tower)
    
    def test_water_cooled_update_load(self):
        """Test updating the water-cooled chiller with a new load."""
        # Connect cooling tower first
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Set load to 50% of capacity
        self.water_cooled_chiller.update_load(
            load=250,  # 250 tons (50% of capacity)
            entering_chilled_water_temp=54,
            chilled_water_flow=1200,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        self.assertEqual(self.water_cooled_chiller.current_load, 250)
        self.assertEqual(self.water_cooled_chiller.entering_chilled_water_temp, 54)
        
        # Verify that leaving water temp is maintained near setpoint
        self.assertAlmostEqual(self.water_cooled_chiller.leaving_chilled_water_temp, 44, delta=0.5)
        
        # Verify that the cooling tower was also updated
        self.assertGreater(self.cooling_tower.current_load, 0)
        self.assertGreater(self.cooling_tower.fan_speed, 0)
        
        # Verify COP is calculated and reasonable
        self.assertGreater(self.water_cooled_chiller.current_cop, 0)
        self.assertLess(self.water_cooled_chiller.current_cop, 10)  # Reasonable upper bound
    
    def test_air_cooled_update_load(self):
        """Test updating the air-cooled chiller with a new load."""
        # Set load to 50% of capacity
        self.air_cooled_chiller.update_load(
            load=150,  # 150 tons (50% of capacity)
            entering_chilled_water_temp=54,
            chilled_water_flow=720,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        self.assertEqual(self.air_cooled_chiller.current_load, 150)
        self.assertEqual(self.air_cooled_chiller.entering_chilled_water_temp, 54)
        self.assertEqual(self.air_cooled_chiller.entering_condenser_temp, 95)  # Uses dry bulb
        
        # Verify that leaving water temp is maintained near setpoint
        self.assertAlmostEqual(self.air_cooled_chiller.leaving_chilled_water_temp, 44, delta=0.5)
        
        # Verify COP is calculated and reasonable
        self.assertGreater(self.air_cooled_chiller.current_cop, 0)
        self.assertLess(self.air_cooled_chiller.current_cop, 5)  # Lower than water-cooled
    
    def test_capacity_limits(self):
        """Test chiller behavior at capacity limits."""
        # Connect cooling tower to water-cooled chiller
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Test water-cooled chiller at overload (120% capacity)
        self.water_cooled_chiller.update_load(
            load=600,  # 120% of capacity
            entering_chilled_water_temp=54,
            chilled_water_flow=1200,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        # Chiller should limit to maximum capacity
        self.assertEqual(self.water_cooled_chiller.current_load, 500)
        
        # Leaving water temp should rise above setpoint
        self.assertGreater(self.water_cooled_chiller.leaving_chilled_water_temp, 44)
        
        # Test air-cooled chiller below minimum part load
        self.air_cooled_chiller.update_load(
            load=30,  # 10% of capacity - below minimum
            entering_chilled_water_temp=54,
            chilled_water_flow=720,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        # Chiller should operate at minimum part load
        self.assertEqual(self.air_cooled_chiller.current_load, 
                         self.air_cooled_chiller.capacity * self.air_cooled_chiller.min_part_load_ratio)
    
    def test_cop_vs_load_relationship(self):
        """Test relationship between load and COP."""
        # Connect cooling tower to water-cooled chiller
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Test different load levels for water-cooled chiller
        water_cooled_loads = [50, 200, 350, 500]  # 10% to 100% of capacity
        water_cooled_cops = []
        
        for load in water_cooled_loads:
            self.water_cooled_chiller.update_load(
                load=load,
                entering_chilled_water_temp=54,
                chilled_water_flow=1200,
                ambient_wet_bulb=76,
                ambient_dry_bulb=95
            )
            water_cooled_cops.append(self.water_cooled_chiller.current_cop)
        
        # COP should be best around 70-80% load, worse at extremes
        self.assertLess(water_cooled_cops[0], water_cooled_cops[1])  # 10% vs 40%
        self.assertLess(water_cooled_cops[3], water_cooled_cops[2])  # 100% vs 70%
        
        # Test different load levels for air-cooled chiller
        air_cooled_loads = [45, 120, 210, 300]  # 15% to 100% of capacity
        air_cooled_cops = []
        
        for load in air_cooled_loads:
            self.air_cooled_chiller.update_load(
                load=load,
                entering_chilled_water_temp=54,
                chilled_water_flow=720,
                ambient_wet_bulb=76,
                ambient_dry_bulb=95
            )
            air_cooled_cops.append(self.air_cooled_chiller.current_cop)
        
        # Similar pattern for air-cooled
        self.assertLess(air_cooled_cops[0], air_cooled_cops[1])  # 15% vs 40%
        self.assertLess(air_cooled_cops[3], air_cooled_cops[2])  # 100% vs 70%
        
        # Air-cooled COP should always be lower than water-cooled
        self.assertLess(max(air_cooled_cops), max(water_cooled_cops))
    
    def test_condenser_temp_effect(self):
        """Test effect of condenser temperature on performance."""
        # Connect cooling tower to water-cooled chiller
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Test with different wet bulb temperatures (affects condenser water temp)
        wet_bulbs = [65, 70, 75, 80, 85]
        water_cooled_cops = []
        
        for wb in wet_bulbs:
            self.water_cooled_chiller.update_load(
                load=300,  # 60% load
                entering_chilled_water_temp=54,
                chilled_water_flow=1200,
                ambient_wet_bulb=wb,
                ambient_dry_bulb=wb + 10  # Arbitrary dry bulb for testing
            )
            water_cooled_cops.append(self.water_cooled_chiller.current_cop)
        
        # COP should decrease as wet bulb (and thus condenser temp) increases
        for i in range(len(wet_bulbs) - 1):
            self.assertGreater(water_cooled_cops[i], water_cooled_cops[i+1])
        
        # Test with different dry bulb temperatures for air-cooled
        dry_bulbs = [75, 85, 95, 105, 115]
        air_cooled_cops = []
        
        for db in dry_bulbs:
            self.air_cooled_chiller.update_load(
                load=180,  # 60% load
                entering_chilled_water_temp=54,
                chilled_water_flow=720,
                ambient_wet_bulb=76,  # Arbitrary constant wet bulb
                ambient_dry_bulb=db
            )
            air_cooled_cops.append(self.air_cooled_chiller.current_cop)
        
        # COP should decrease as dry bulb increases
        for i in range(len(dry_bulbs) - 1):
            self.assertGreater(air_cooled_cops[i], air_cooled_cops[i+1])
    
    def test_power_consumption(self):
        """Test chiller power consumption calculation."""
        # Connect cooling tower to water-cooled chiller
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Update both chillers with 50% load
        self.water_cooled_chiller.update_load(
            load=250,
            entering_chilled_water_temp=54,
            chilled_water_flow=1200,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        self.air_cooled_chiller.update_load(
            load=150,
            entering_chilled_water_temp=54,
            chilled_water_flow=720,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        # Calculate power consumption
        water_cooled_power = self.water_cooled_chiller.calculate_power_consumption()
        air_cooled_power = self.air_cooled_chiller.calculate_power_consumption()
        
        # Power should be positive and reasonable
        self.assertGreater(water_cooled_power, 0)
        self.assertGreater(air_cooled_power, 0)
        
        # Power should relate to capacity and COP
        self.assertAlmostEqual(water_cooled_power, 
                              (self.water_cooled_chiller.current_load * 3.517) / self.water_cooled_chiller.current_cop, 
                              delta=1)
        
        self.assertAlmostEqual(air_cooled_power, 
                              (self.air_cooled_chiller.current_load * 3.517) / self.air_cooled_chiller.current_cop, 
                              delta=1)
        
        # Air-cooled should use more power per ton due to lower COP
        water_cooled_kw_per_ton = water_cooled_power / self.water_cooled_chiller.current_load
        air_cooled_kw_per_ton = air_cooled_power / self.air_cooled_chiller.current_load
        self.assertGreater(air_cooled_kw_per_ton, water_cooled_kw_per_ton)
    
    def test_integrated_system_energy(self):
        """Test total system energy including cooling tower for water-cooled chiller."""
        # Connect cooling tower to water-cooled chiller
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Update chiller at 60% load
        self.water_cooled_chiller.update_load(
            load=300,
            entering_chilled_water_temp=54,
            chilled_water_flow=1200,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        # Calculate chiller power
        chiller_power = self.water_cooled_chiller.calculate_power_consumption()
        
        # Calculate cooling tower power
        tower_power = self.cooling_tower.calculate_power_consumption()
        
        # Total system power
        system_power = self.water_cooled_chiller.calculate_system_power_consumption()
        
        # System power should equal chiller power + tower power
        self.assertAlmostEqual(system_power, chiller_power + tower_power, delta=0.1)
        
        # Calculate energy for 1 hour
        system_energy = self.water_cooled_chiller.calculate_system_energy_consumption(hours=1)
        
        # Energy should be close to power * time
        self.assertAlmostEqual(system_energy, system_power * 1, delta=0.1)
    
    def test_leaving_water_temp_control(self):
        """Test control of leaving chilled water temperature."""
        # Connect cooling tower to water-cooled chiller
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Update chiller with 50% load and different setpoint
        self.water_cooled_chiller.set_leaving_water_temp_setpoint(42)
        self.water_cooled_chiller.update_load(
            load=250,
            entering_chilled_water_temp=54,
            chilled_water_flow=1200,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        # Verify LCWT is near new setpoint
        self.assertAlmostEqual(self.water_cooled_chiller.leaving_chilled_water_temp, 42, delta=0.5)
        
        # COP should be lower with colder LCWT
        original_cop = self.water_cooled_chiller.current_cop
        
        # Test with even colder setpoint
        self.water_cooled_chiller.set_leaving_water_temp_setpoint(38)
        self.water_cooled_chiller.update_load(
            load=250,
            entering_chilled_water_temp=54,
            chilled_water_flow=1200,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        # LCWT should be near new setpoint
        self.assertAlmostEqual(self.water_cooled_chiller.leaving_chilled_water_temp, 38, delta=0.5)
        
        # COP should be lower with even colder LCWT
        colder_cop = self.water_cooled_chiller.current_cop
        self.assertLess(colder_cop, original_cop)
        
    def test_get_process_variables(self):
        """Test that Chiller returns a dictionary of all process variables."""
        # Connect cooling tower to water-cooled chiller
        self.water_cooled_chiller.connect_cooling_tower(self.cooling_tower)
        
        # Update chillers with some load
        self.water_cooled_chiller.update_load(
            load=250,
            entering_chilled_water_temp=54,
            chilled_water_flow=1200,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        self.air_cooled_chiller.update_load(
            load=150,
            entering_chilled_water_temp=54,
            chilled_water_flow=720,
            ambient_wet_bulb=76,
            ambient_dry_bulb=95
        )
        
        # Get process variables for both chiller types
        water_cooled_vars = self.water_cooled_chiller.get_process_variables()
        air_cooled_vars = self.air_cooled_chiller.get_process_variables()
        
        # Check that they're dictionaries
        self.assertIsInstance(water_cooled_vars, dict)
        self.assertIsInstance(air_cooled_vars, dict)
        
        # Check that they contain essential state variables
        essential_vars = [
            "name", "cooling_type", "capacity", "current_load", "load_ratio", 
            "current_cop", "entering_chilled_water_temp", "leaving_chilled_water_temp", 
            "entering_condenser_temp", "chilled_water_flow", "power_consumption"
        ]
        
        for var in essential_vars:
            self.assertIn(var, water_cooled_vars)
            self.assertIn(var, air_cooled_vars)
            
        # Check that values match the actual object properties
        self.assertEqual(water_cooled_vars["name"], self.water_cooled_chiller.name)
        self.assertEqual(water_cooled_vars["cooling_type"], self.water_cooled_chiller.cooling_type)
        self.assertEqual(water_cooled_vars["capacity"], self.water_cooled_chiller.capacity)
        self.assertEqual(water_cooled_vars["current_load"], self.water_cooled_chiller.current_load)
        self.assertEqual(water_cooled_vars["entering_chilled_water_temp"], self.water_cooled_chiller.entering_chilled_water_temp)
        self.assertEqual(water_cooled_vars["leaving_chilled_water_temp"], self.water_cooled_chiller.leaving_chilled_water_temp)
        
        # Check that water-cooled includes cooling tower info
        self.assertIn("condenser_water_flow", water_cooled_vars)
        self.assertIn("has_cooling_tower", water_cooled_vars)
        self.assertIn("cooling_tower_name", water_cooled_vars)
        self.assertTrue(water_cooled_vars["has_cooling_tower"])
        self.assertEqual(water_cooled_vars["cooling_tower_name"], self.cooling_tower.name)
        
        # Air-cooled should not have these variables
        self.assertNotIn("condenser_water_flow", air_cooled_vars)
        self.assertNotIn("cooling_tower_name", air_cooled_vars)
    
    def test_get_process_variables_metadata(self):
        """Test that Chiller provides metadata for all process variables."""
        # Get metadata
        metadata = Chiller.get_process_variables_metadata()
        
        # Check that it's a dictionary
        self.assertIsInstance(metadata, dict)
        
        # Check that it contains metadata for essential state variables
        essential_vars = [
            "name", "cooling_type", "capacity", "current_load", "load_ratio", 
            "current_cop", "entering_chilled_water_temp", "leaving_chilled_water_temp"
        ]
        
        for var in essential_vars:
            self.assertIn(var, metadata)
            
        # Check that each variable has the required metadata fields
        for var_name, var_metadata in metadata.items():
            self.assertIn("type", var_metadata)
            self.assertIn("label", var_metadata)
            self.assertIn("description", var_metadata)
            
        # Check specific metadata entries for correctness
        self.assertEqual(metadata["current_load"]["type"], float)
        self.assertEqual(metadata["current_load"]["label"], "Current Load")
        self.assertEqual(metadata["current_load"]["unit"], "tons")
        
        self.assertEqual(metadata["name"]["type"], str)
        self.assertEqual(metadata["cooling_type"]["type"], str)
        self.assertEqual(metadata["has_cooling_tower"]["type"], bool)
        
        # Check that options are provided for enumerated types
        self.assertIn("options", metadata["cooling_type"])
        self.assertIn("water_cooled", metadata["cooling_type"]["options"])
        self.assertIn("air_cooled", metadata["cooling_type"]["options"])
        
        # Check that water-cooled specific variables are included
        self.assertIn("condenser_water_flow", metadata)
        self.assertIn("cooling_tower_name", metadata)

if __name__ == '__main__':
    unittest.main()